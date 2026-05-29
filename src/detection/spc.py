"""
spc.py
------
Statistical Process Control — Shewhart control charts.
Détecte les anomalies par franchissement des limites UCL/LCL.
"""

from collections import deque
from ..simulator.generator import SensorReading
from .levels import AlertLevel, DetectionResult


class ShewhartDetector:
    """
    Graphique de contrôle de Shewhart (3-sigma).

    UCL = mean + 3σ  (Upper Control Limit)
    LCL = mean - 3σ  (Lower Control Limit)
    UWL = mean + 2σ  (Upper Warning Limit)
    LWL = mean - 2σ  (Lower Warning Limit)

    - Valeur entre ±2σ  → NORMAL
    - Valeur entre 2σ et 3σ → WARNING
    - Valeur au-delà de ±3σ  → CRITICAL
    """

    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self._windows: dict[str, deque] = {}

    def _window(self, sensor: str) -> deque:
        if sensor not in self._windows:
            self._windows[sensor] = deque(maxlen=self.window_size)
        return self._windows[sensor]

    def get_limits(self, sensor: str) -> dict:
        """Retourne UCL, LCL, UWL, LWL, mean, sigma pour le capteur."""
        w = list(self._window(sensor))
        if len(w) < 5:
            return {"ucl": None, "lcl": None, "uwl": None, "lwl": None, "mean": None, "sigma": None}
        import numpy as np
        mean  = float(np.mean(w))
        sigma = float(np.std(w))
        return {
            "ucl":   round(mean + 3 * sigma, 4),
            "lcl":   round(mean - 3 * sigma, 4),
            "uwl":   round(mean + 2 * sigma, 4),
            "lwl":   round(mean - 2 * sigma, 4),
            "mean":  round(mean, 4),
            "sigma": round(sigma, 4),
        }

    def analyze(self, reading: SensorReading) -> DetectionResult:
        from ..simulator.config import SENSOR_CONFIG
        w     = self._window(reading.sensor)
        value = reading.value
        cfg   = SENSOR_CONFIG.get(reading.sensor, {})
        unit  = cfg.get("unit", reading.unit)

        # Ajouter la valeur à la fenêtre
        w.append(value)

        limits = self.get_limits(reading.sensor)
        if limits["mean"] is None:
            # Pas encore assez de données
            return DetectionResult(
                sensor=reading.sensor, value=value, unit=unit,
                level=AlertLevel.NORMAL, method="spc",
                reason=f"SPC: calibration en cours ({len(w)}/{self.window_size})",
                timestamp=reading.timestamp,
            )

        mean  = limits["mean"]
        sigma = limits["sigma"]

        if sigma == 0:
            return DetectionResult(
                sensor=reading.sensor, value=value, unit=unit,
                level=AlertLevel.NORMAL, method="spc",
                reason=f"SPC: valeur stable (σ=0)",
                timestamp=reading.timestamp,
            )

        z = (value - mean) / sigma

        if abs(z) > 3:
            level  = AlertLevel.CRITICAL
            reason = (f"SPC CRITIQUE — valeur {value} {unit} dépasse UCL/LCL "
                      f"(±3σ : [{limits['lcl']:.2f}, {limits['ucl']:.2f}])")
        elif abs(z) > 2:
            level  = AlertLevel.WARNING
            reason = (f"SPC ALERTE — valeur {value} {unit} dépasse zone d'avertissement "
                      f"(±2σ : [{limits['lwl']:.2f}, {limits['uwl']:.2f}])")
        else:
            level  = AlertLevel.NORMAL
            reason = f"SPC: valeur normale ({value} {unit}, z={z:.2f})"

        return DetectionResult(
            sensor=reading.sensor, value=value, unit=unit,
            level=level, method="spc",
            reason=reason,
            timestamp=reading.timestamp,
            z_score=round(z, 4),
            expected_min=limits["lcl"],
            expected_max=limits["ucl"],
        )

    def get_chart_data(self, sensor: str) -> dict:
        """Retourne les données pour le graphique de contrôle."""
        w      = list(self._window(sensor))
        limits = self.get_limits(sensor)
        violations = []
        if limits["mean"] is not None and limits["sigma"] and limits["sigma"] > 0:
            mean  = limits["mean"]
            sigma = limits["sigma"]
            for i, v in enumerate(w):
                z = (v - mean) / sigma
                if abs(z) > 3:
                    violations.append({"index": i, "value": v, "level": "CRITICAL"})
                elif abs(z) > 2:
                    violations.append({"index": i, "value": v, "level": "WARNING"})
        return {
            "values":     [round(v, 4) for v in w],
            "violations": violations,
            **limits,
        }
