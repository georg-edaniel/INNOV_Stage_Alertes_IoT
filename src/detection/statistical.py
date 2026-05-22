"""
statistical.py
--------------
Détection d'anomalies par méthodes statistiques :
  - Z-score          : détecte les valeurs qui s'éloignent de la moyenne (en nb d'écarts-types)
  - IQR              : détecte les valeurs hors de l'intervalle interquartile
  - Isolation Forest : détection non-supervisée par arbres d'isolation (scikit-learn)

Ces méthodes s'adaptent aux données observées — elles détectent
les dérives progressives que les seuils fixes peuvent rater.
"""

from collections import deque
import numpy as np
from sklearn.ensemble import IsolationForest

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


class IsolationForestDetector:
    """
    Détecteur basé sur Isolation Forest (scikit-learn).

    L'algorithme construit 100 arbres de décision aléatoires et mesure
    la longueur du chemin pour isoler chaque valeur. Les anomalies
    sont isolées plus rapidement (chemin plus court = score négatif).

    Paramètres :
        window_size   : taille de la fenêtre d'entraînement (défaut 100)
        min_samples   : nb de lectures avant d'activer le modèle (défaut 20)
        contamination : proportion d'anomalies attendue (défaut 0.05 = 5 %)
        retrain_every : réentraîne le modèle tous les N points (défaut 20)
    """

    def __init__(
        self,
        window_size:   int   = 100,
        min_samples:   int   = 20,
        contamination: float = 0.05,
        retrain_every: int   = 20,
    ):
        self.window_size   = window_size
        self.min_samples   = min_samples
        self.contamination = contamination
        self.retrain_every = retrain_every
        self._windows: dict[str, deque]          = {s: deque(maxlen=window_size) for s in SENSOR_CONFIG}
        self._models:  dict[str, IsolationForest] = {}
        self._counts:  dict[str, int]            = {s: 0 for s in SENSOR_CONFIG}

    def _train(self, sensor: str) -> None:
        """Entraîne (ou réentraîne) le modèle Isolation Forest sur la fenêtre courante."""
        arr = np.array(self._windows[sensor]).reshape(-1, 1)
        model = IsolationForest(
            n_estimators  = 100,
            contamination = self.contamination,
            random_state  = 42,
            n_jobs        = 1,
        )
        model.fit(arr)
        self._models[sensor] = model

    def analyze(self, reading: SensorReading) -> DetectionResult:
        cfg    = SENSOR_CONFIG[reading.sensor]
        window = self._windows[reading.sensor]
        value  = reading.value
        sensor = reading.sensor

        window.append(value)
        self._counts[sensor] = self._counts.get(sensor, 0) + 1

        # Pas assez de données
        if len(window) < self.min_samples:
            return DetectionResult(
                sensor    = sensor,
                value     = value,
                unit      = cfg["unit"],
                level     = AlertLevel.NORMAL,
                method    = "isolation_forest",
                reason    = f"Initialisation ({len(window)}/{self.min_samples} points)",
                timestamp = reading.timestamp,
            )

        # Entraîner / réentraîner périodiquement
        if sensor not in self._models or self._counts[sensor] % self.retrain_every == 0:
            self._train(sensor)

        model = self._models[sensor]
        x     = np.array([[value]])
        score = float(model.decision_function(x)[0])  # > 0 = normal, < 0 = anomalie
        pred  = int(model.predict(x)[0])               # 1 = normal, -1 = anomalie

        if pred == -1:
            # Distinguer WARNING vs CRITICAL selon l'amplitude du score négatif
            if score < -0.1:
                level  = AlertLevel.CRITICAL
                reason = (
                    f"Isolation Forest : anomalie critique (score={score:.3f}) "
                    f"— valeur : {value} {cfg['unit']}"
                )
            else:
                level  = AlertLevel.WARNING
                reason = (
                    f"Isolation Forest : anomalie detectee (score={score:.3f}) "
                    f"— valeur : {value} {cfg['unit']}"
                )
        else:
            level  = AlertLevel.NORMAL
            reason = (
                f"Isolation Forest : normal (score={score:.3f}) "
                f"— valeur : {value} {cfg['unit']}"
            )

        return DetectionResult(
            sensor    = sensor,
            value     = value,
            unit      = cfg["unit"],
            level     = level,
            method    = "isolation_forest",
            reason    = reason,
            timestamp = reading.timestamp,
        )

    def reset(self, sensor: str | None = None) -> None:
        """Vide la fenêtre et le modèle d'un capteur (ou tous)."""
        targets = [sensor] if sensor else list(SENSOR_CONFIG)
        for s in targets:
            self._windows[s].clear()
            self._models.pop(s, None)
            self._counts[s] = 0
