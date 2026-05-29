"""
cusum.py
--------
Détecteur CUSUM (Cumulative Sum Control Chart) — Shewhart amélioré.

Le CUSUM accumule les déviations successives par rapport à une cible μ₀,
ce qui lui permet de détecter des dérives progressives que le Z-score rate.

Algorithme (Tabular CUSUM) :
    C+_n = max(0, C+_{n-1} + (x_n - μ₀ - k))
    C-_n = max(0, C-_{n-1} - (x_n - μ₀ - k))

    k = k_factor * σ   (slack allowable, typiquement 0.5 σ)
    h = h_factor * σ   (seuil décisionnel, typiquement 4–5 σ)

    Alarme si C+_n > h (dérive vers le haut) ou C-_n > h (dérive vers le bas)

Seuils retournés :
    NORMAL   : C+ ≤ h/2  et  C- ≤ h/2
    WARNING  : C+ ∈ (h/2, h]  ou  C- ∈ (h/2, h]
    CRITICAL : C+ > h  ou  C- > h
"""

from collections import deque
import numpy as np

from ..simulator.generator import SensorReading
from .levels import AlertLevel, DetectionResult

_MIN_SAMPLES = 15  # nombre minimum de points avant de signaler


class CUSUMDetector:
    """
    Détecteur CUSUM à fenêtre glissante avec warmup explicite.

    Parameters
    ----------
    window_size : int
        Taille de la fenêtre pour estimer μ₀ et σ (défaut 40).
    k_factor : float
        Slack en unités sigma (défaut 0.5 — standard industriel).
    h_factor : float
        Seuil décisionnel en unités sigma (défaut 5.0 — standard ARL≈500).
    warmup_samples : int
        Nombre de points à collecter avant toute alarme (défaut 30).
    """

    def __init__(
        self,
        window_size: int = 40,
        k_factor: float = 0.5,
        h_factor: float = 5.0,
        warmup_samples: int = 30,
    ):
        self.window_size    = window_size
        self.k_factor       = k_factor
        self.h_factor       = h_factor
        self.warmup_samples = warmup_samples
        # Par capteur : historique des valeurs brutes
        self._data:         dict[str, deque] = {}
        # Par capteur : compteur de warmup
        self._warmup_count: dict[str, int]   = {}
        # Par capteur : accumulateurs CUSUM (C+ et C-)
        self._cusum_pos: dict[str, float] = {}
        self._cusum_neg: dict[str, float] = {}
        # Par capteur : séries C+/C- pour visualisation
        self._series_pos: dict[str, list] = {}
        self._series_neg: dict[str, list] = {}
        self._timestamps:  dict[str, list] = {}

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def analyze(self, reading: SensorReading) -> DetectionResult:
        """Analyse une lecture et retourne le résultat CUSUM."""
        sensor = reading.sensor
        value  = float(reading.value)

        # Initialisation par capteur
        if sensor not in self._data:
            self._data[sensor]         = deque(maxlen=self.window_size * 3)
            self._warmup_count[sensor] = 0
            self._cusum_pos[sensor]    = 0.0
            self._cusum_neg[sensor]    = 0.0
            self._series_pos[sensor]   = []
            self._series_neg[sensor]   = []
            self._timestamps[sensor]   = []

        self._data[sensor].append(value)
        self._warmup_count[sensor] += 1
        window = list(self._data[sensor])

        unit = getattr(reading, "unit", "?")

        # Phase warmup : NORMAL sans alarme
        if self._warmup_count[sensor] <= self.warmup_samples:
            return DetectionResult(
                level=AlertLevel.NORMAL,
                method="cusum",
                reason=f"CUSUM : warmup ({self._warmup_count[sensor]}/{self.warmup_samples})",
                value=value,
                unit=unit,
                sensor=sensor,
            )

        # Pas assez de données : NORMAL sans bruit
        if len(window) < _MIN_SAMPLES:
            return DetectionResult(
                level=AlertLevel.NORMAL,
                method="cusum",
                reason="CUSUM : initialisation (pas assez de données)",
                value=value,
                unit=unit,
                sensor=sensor,
            )

        # Estimation robuste μ₀ et σ sur la fenêtre (sans le dernier point)
        ref = np.array(window[:-1])
        mu    = float(np.median(ref))          # médiane plus robuste aux outliers
        sigma = float(np.std(ref)) or 1e-6

        k = self.k_factor * sigma
        h = self.h_factor * sigma

        # Mise à jour des accumulateurs
        deviation = value - mu
        self._cusum_pos[sensor] = max(0.0, self._cusum_pos[sensor] + deviation - k)
        self._cusum_neg[sensor] = max(0.0, self._cusum_neg[sensor] - deviation - k)

        c_pos = self._cusum_pos[sensor]
        c_neg = self._cusum_neg[sensor]

        # Stocker pour visualisation (50 derniers points)
        self._series_pos[sensor].append(round(c_pos, 4))
        self._series_neg[sensor].append(round(c_neg, 4))
        self._timestamps[sensor].append(
            reading.created_at.isoformat() if hasattr(reading, "created_at") and reading.created_at else None
        )
        if len(self._series_pos[sensor]) > 200:
            self._series_pos[sensor] = self._series_pos[sensor][-200:]
            self._series_neg[sensor] = self._series_neg[sensor][-200:]
            self._timestamps[sensor] = self._timestamps[sensor][-200:]

        # ── Décision ──────────────────────────────────────────────────
        if c_pos > h or c_neg > h:
            direction = "hausse" if c_pos > c_neg else "baisse"
            reason = (
                f"CUSUM dérive {direction} : C+={c_pos:.2f} C-={c_neg:.2f} > h={h:.2f} "
                f"(μ={mu:.2f}, σ={sigma:.2f})"
            )
            # Réinitialiser l'accumulateur qui a déclenché
            if c_pos > h:
                self._cusum_pos[sensor] = 0.0
            if c_neg > h:
                self._cusum_neg[sensor] = 0.0
            return DetectionResult(
                level=AlertLevel.CRITICAL,
                method="cusum",
                reason=reason,
                value=value,
                unit=unit,
                sensor=sensor,
                z_score=round(deviation / sigma, 3),
            )

        if c_pos > h / 2 or c_neg > h / 2:
            direction = "hausse" if c_pos > c_neg else "baisse"
            reason = (
                f"CUSUM dérive précoce {direction} : C+={c_pos:.2f} C-={c_neg:.2f} "
                f"(seuil h={h:.2f})"
            )
            return DetectionResult(
                level=AlertLevel.WARNING,
                method="cusum",
                reason=reason,
                value=value,
                unit=unit,
                sensor=sensor,
                z_score=round(deviation / sigma, 3),
            )

        return DetectionResult(
            level=AlertLevel.NORMAL,
            method="cusum",
            reason="CUSUM normal",
            value=value,
            unit=unit,
            sensor=sensor,
            z_score=round(deviation / sigma, 3),
        )

    def get_chart_data(self, sensor: str) -> dict:
        """
        Retourne les séries C+ et C- pour le graphique.
        Inclut les limites h (CRITICAL) et h/2 (WARNING).
        """
        if sensor not in self._data or len(self._data[sensor]) < _MIN_SAMPLES:
            return {"cusum_pos": [], "cusum_neg": [], "h": None, "h_warn": None, "timestamps": []}

        window = list(self._data[sensor])
        ref    = np.array(window[:-1])
        sigma  = float(np.std(ref)) or 1e-6
        h      = self.h_factor * sigma
        h_warn = h / 2.0

        return {
            "cusum_pos":  self._series_pos.get(sensor, [])[-60:],
            "cusum_neg":  self._series_neg.get(sensor, [])[-60:],
            "h":          round(h, 4),
            "h_warn":     round(h_warn, 4),
            "timestamps": self._timestamps.get(sensor, [])[-60:],
        }

    def reset(self, sensor: str | None = None):
        """Réinitialise les accumulateurs CUSUM (un capteur ou tous)."""
        sensors = [sensor] if sensor else list(self._data.keys())
        for s in sensors:
            self._cusum_pos[s] = 0.0
            self._cusum_neg[s] = 0.0
