"""
rules.py
--------
Détection d'anomalies par règles métier (seuils fixes).
C'est la méthode la plus simple et la plus explicable.

Logique :
  - Valeur dans la plage normale  → NORMAL
  - Valeur dans la plage warning  → WARNING
  - Valeur hors plage warning     → CRITICAL
"""

from ..alerts.threshold_config import get_sensor
from ..simulator.generator import SensorReading
from .levels import AlertLevel, DetectionResult


class RuleBasedDetector:
    """
    Détecteur basé sur des seuils définis dynamiquement (configurables via l'API).

    C'est la première ligne de défense : rapide, déterministe,
    facile à expliquer aux opérateurs.
    """

    def analyze(self, reading: SensorReading) -> DetectionResult:
        cfg   = get_sensor(reading.sensor)
        value = reading.value

        normal_min  = cfg["normal"]["min"]
        normal_max  = cfg["normal"]["max"]
        warning_min = cfg["warning"]["min"]
        warning_max = cfg["warning"]["max"]

        if normal_min <= value <= normal_max:
            level  = AlertLevel.NORMAL
            reason = f"Valeur normale ({value} {cfg['unit']})"

        elif warning_min <= value <= warning_max:
            level  = AlertLevel.WARNING
            if value > normal_max:
                reason = f"Valeur élevée : {value} {cfg['unit']} (seuil normal max : {normal_max})"
            else:
                reason = f"Valeur basse : {value} {cfg['unit']} (seuil normal min : {normal_min})"

        else:
            level  = AlertLevel.CRITICAL
            if value > warning_max:
                reason = f"CRITIQUE — valeur trop élevée : {value} {cfg['unit']} (seuil max : {warning_max})"
            else:
                reason = f"CRITIQUE — valeur trop basse : {value} {cfg['unit']} (seuil min : {warning_min})"

        return DetectionResult(
            sensor       = reading.sensor,
            value        = value,
            unit         = cfg["unit"],
            level        = level,
            method       = "rules",
            reason       = reason,
            timestamp    = reading.timestamp,
            expected_min = normal_min,
            expected_max = normal_max,
        )

    def analyze_batch(self, readings: list[SensorReading]) -> list[DetectionResult]:
        return [self.analyze(r) for r in readings]
