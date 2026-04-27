"""
statistical.py
--------------
Détection d'anomalies par méthodes statistiques :
  - Z-score  : détecte les valeurs qui s'éloignent de la moyenne (en nb d'écarts-types)
  - IQR      : détecte les valeurs hors de l'intervalle interquartile

Ces méthodes s'adaptent aux données observées — elles détectent
les dérives progressives que les seuils fixes peuvent rater.
"""

from collections import deque
import numpy as np

from ..simulator.config import SENSOR_CONFIG
from ..simulator.generator import SensorReading
from .levels import AlertLevel, DetectionResult


class ZScoreDetector:
    """
    Détecteur Z-score sur fenêtre glissante.

    Le Z-score mesure combien d'écarts-types une valeur s'éloigne
    de la moyenne de la fenêtre.

    Seuils par défaut :
        |z| > 2  → WARNING
        |z| > 3  → CRITICAL
    """

    def __init__(self, window_size: int = 30, warning_threshold: float = 2.0, critical_threshold: float = 3.0):
        self.window_size         = window_size
        self.warning_threshold   = warning_threshold
        self.critical_threshold  = critical_threshold
        # Une fenêtre par capteur
        self._windows: dict[str, deque] = {
            sensor: deque(maxlen=window_size) for sensor in SENSOR_CONFIG
        }

    def analyze(self, reading: SensorReading) -> DetectionResult:
        cfg    = SENSOR_CONFIG[reading.sensor]
        window = self._windows[reading.sensor]
        value  = reading.value

        # Pas assez de données : on ne peut pas calculer le Z-score
        if len(window) < 5:
            window.append(value)
            return DetectionResult(
                sensor    = reading.sensor,
                value     = value,
                unit      = cfg["unit"],
                level     = AlertLevel.NORMAL,
                method    = "zscore",
                reason    = f"Initialisation fenêtre ({len(window)}/{self.window_size} points)",
                timestamp = reading.timestamp,
            )

        # Calcul sur l'historique AVANT d'ajouter la nouvelle valeur
        arr    = np.array(window)
        mean   = float(arr.mean())
        std    = float(arr.std())
        window.append(value)

        # Si std = 0 (signal constant en test), on utilise le bruit typique du capteur
        if std == 0:
            std = cfg["noise_std"]
        z = min(abs((value - mean) / std), 999.0)

        if z >= self.critical_threshold:
            level  = AlertLevel.CRITICAL
            reason = f"Z-score critique : {z:.2f} (seuil : {self.critical_threshold}) — valeur : {value} {cfg['unit']}"
        elif z >= self.warning_threshold:
            level  = AlertLevel.WARNING
            reason = f"Z-score élevé : {z:.2f} (seuil : {self.warning_threshold}) — valeur : {value} {cfg['unit']}"
        else:
            level  = AlertLevel.NORMAL
            reason = f"Z-score normal : {z:.2f} — valeur : {value} {cfg['unit']}"

        return DetectionResult(
            sensor    = reading.sensor,
            value     = value,
            unit      = cfg["unit"],
            level     = level,
            method    = "zscore",
            reason    = reason,
            timestamp = reading.timestamp,
            z_score   = round(z, 4),
        )

    def reset(self, sensor: str | None = None):
        """Vide la fenêtre d'un capteur (ou tous si sensor=None)."""
        targets = [sensor] if sensor else list(SENSOR_CONFIG)
        for s in targets:
            self._windows[s].clear()


class IQRDetector:
    """
    Détecteur basé sur l'intervalle interquartile (IQR) sur fenêtre glissante.

    Robuste aux valeurs extrêmes ponctuelles.
    Seuils : valeur hors [Q1 - k*IQR, Q3 + k*IQR]
        k=1.5 → WARNING
        k=3.0 → CRITICAL
    """

    def __init__(self, window_size: int = 30, warning_k: float = 1.5, critical_k: float = 3.0):
        self.window_size = window_size
        self.warning_k   = warning_k
        self.critical_k  = critical_k
        self._windows: dict[str, deque] = {
            sensor: deque(maxlen=window_size) for sensor in SENSOR_CONFIG
        }

    def analyze(self, reading: SensorReading) -> DetectionResult:
        cfg    = SENSOR_CONFIG[reading.sensor]
        window = self._windows[reading.sensor]
        value  = reading.value

        if len(window) < 5:
            window.append(value)
            return DetectionResult(
                sensor    = reading.sensor,
                value     = value,
                unit      = cfg["unit"],
                level     = AlertLevel.NORMAL,
                method    = "iqr",
                reason    = f"Initialisation fenêtre ({len(window)}/{self.window_size} points)",
                timestamp = reading.timestamp,
            )

        # Calcul sur l'historique AVANT d'ajouter la nouvelle valeur
        arr = np.array(window)
        q1  = float(np.percentile(arr, 25))
        q3  = float(np.percentile(arr, 75))
        iqr = q3 - q1
        window.append(value)

        # Si IQR = 0 (toutes valeurs identiques), on élargit avec l'écart-type
        if iqr == 0:
            mean = float(arr.mean())
            std  = float(arr.std()) or 1.0
            lower_warn = mean - self.warning_k  * std
            upper_warn = mean + self.warning_k  * std
            lower_crit = mean - self.critical_k * std
            upper_crit = mean + self.critical_k * std
        else:
            lower_warn = q1 - self.warning_k  * iqr
            upper_warn = q3 + self.warning_k  * iqr
            lower_crit = q1 - self.critical_k * iqr
            upper_crit = q3 + self.critical_k * iqr

        if value < lower_crit or value > upper_crit:
            level  = AlertLevel.CRITICAL
            reason = f"IQR critique : {value} {cfg['unit']} hors [{lower_crit:.2f}, {upper_crit:.2f}]"
        elif value < lower_warn or value > upper_warn:
            level  = AlertLevel.WARNING
            reason = f"IQR warning : {value} {cfg['unit']} hors [{lower_warn:.2f}, {upper_warn:.2f}]"
        else:
            level  = AlertLevel.NORMAL
            reason = f"IQR normal : {value} {cfg['unit']} dans [{lower_warn:.2f}, {upper_warn:.2f}]"

        return DetectionResult(
            sensor       = reading.sensor,
            value        = value,
            unit         = cfg["unit"],
            level        = level,
            method       = "iqr",
            reason       = reason,
            timestamp    = reading.timestamp,
            expected_min = round(lower_warn, 3),
            expected_max = round(upper_warn, 3),
        )
