"""
engine.py
---------
Moteur principal de détection : combine les 4 détecteurs
et retourne le niveau le plus sévère.

Stratégie : worst-case
    Si règles = WARNING et z-score = CRITICAL → résultat = CRITICAL

Détecteurs :
    1. RuleBasedDetector   — seuils métier fixes par capteur
    2. ZScoreDetector      — écart à la moyenne (NumPy)
    3. IQRDetector         — intervalle interquartile (NumPy)
    4. IsolationForest     — détection non-supervisée ML (scikit-learn)

Cela garantit qu'aucune anomalie ne passe entre les mailles.
"""

from ..simulator.generator import SensorReading
from .levels import AlertLevel, DetectionResult
from .rules import RuleBasedDetector
from .statistical import ZScoreDetector, IQRDetector, IsolationForestDetector

_SEVERITY = {AlertLevel.NORMAL: 0, AlertLevel.WARNING: 1, AlertLevel.CRITICAL: 2}


class AnomalyDetectionEngine:
    """
    Orchestre les 4 détecteurs et fusionne leurs résultats.

    Usage:
        engine = AnomalyDetectionEngine()
        results = engine.analyze_batch(readings)
        for r in results:
            if r.is_anomaly():
                print(r)
    """

    def __init__(self, window_size: int = 30):
        self.rules   = RuleBasedDetector()
        self.zscore  = ZScoreDetector(window_size=window_size)
        self.iqr     = IQRDetector(window_size=window_size)
        self.iforest = IsolationForestDetector(window_size=max(window_size * 3, 100))

    def analyze(self, reading: SensorReading) -> DetectionResult:
        """Analyse une lecture et retourne le résultat le plus sévère."""
        candidates = [
            self.rules.analyze(reading),
            self.zscore.analyze(reading),
            self.iqr.analyze(reading),
            self.iforest.analyze(reading),
        ]
        # Garder le résultat le plus sévère
        worst = max(candidates, key=lambda r: _SEVERITY[r.level])
        return worst

    def analyze_batch(self, readings: list[SensorReading]) -> list[DetectionResult]:
        return [self.analyze(r) for r in readings]

    def summary(self, results: list[DetectionResult]) -> dict:
        """Résumé statistique d'un lot de résultats."""
        total    = len(results)
        normal   = sum(1 for r in results if r.level == AlertLevel.NORMAL)
        warning  = sum(1 for r in results if r.level == AlertLevel.WARNING)
        critical = sum(1 for r in results if r.level == AlertLevel.CRITICAL)
        return {
            "total":    total,
            "normal":   normal,
            "warning":  warning,
            "critical": critical,
            "anomaly_rate": round((warning + critical) / total, 4) if total else 0,
        }
