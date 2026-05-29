"""
engine.py
---------
Moteur principal de détection : combine les 7 détecteurs
via un vote pondéré (Ensemble Voting).

Stratégie : Ensemble Voting pondéré
    CRITICAL si ≥2 votes CRITICAL OU 1 vote CRITICAL conf ≥ 0.9
    WARNING  si ≥2 votes WARNING/CRITICAL
    NORMAL   sinon

Poids des détecteurs :
    rules=2, iforest=1.5, mv_iforest=1.5, cusum=1.5
    zscore=1, iqr=1, autoenc=1

Détecteurs :
    1. RuleBasedDetector           — seuils métier fixes par capteur
    2. ZScoreDetector              — écart à la moyenne (NumPy)
    3. IQRDetector                 — intervalle interquartile (NumPy)
    4. IsolationForest             — détection non-supervisée ML (scikit-learn)
    5. MultivariateIsolationForest — corrélation multi-capteurs
    6. LinearAutoencoderDetector   — erreur de reconstruction PCA (numpy)
    7. CUSUMDetector               — dérive cumulée (Tabular CUSUM)
"""

from ..simulator.generator import SensorReading
from .levels import AlertLevel, DetectionResult
from .rules import RuleBasedDetector
from .statistical import ZScoreDetector, IQRDetector, IsolationForestDetector, MultivariateIsolationForestDetector
from .autoencoder import LinearAutoencoderDetector
from .cusum import CUSUMDetector

_SEVERITY = {AlertLevel.NORMAL: 0, AlertLevel.WARNING: 1, AlertLevel.CRITICAL: 2}

# Poids de vote par détecteur
_WEIGHTS: dict[str, float] = {
    "rules":      2.0,
    "iforest":    1.5,
    "mv_iforest": 1.5,
    "cusum":      1.5,
    "zscore":     1.0,
    "iqr":        1.0,
    "autoenc":    1.0,
}


def _ensemble_vote(candidates: list[DetectionResult]) -> DetectionResult:
    """
    Vote pondéré :
    - CRITICAL si ≥2 votes CRITICAL OU 1 vote CRITICAL conf ≥ 0.9
    - WARNING  si ≥2 votes WARNING/CRITICAL (en poids)
    - NORMAL   sinon
    Retourne le résultat original le plus sévère comme résultat final
    avec method="ensemble".
    """
    critical_weight = 0.0
    warning_weight  = 0.0

    for r in candidates:
        w = _WEIGHTS.get(r.method, 1.0)
        if r.level == AlertLevel.CRITICAL:
            critical_weight += w
            # 1 vote CRITICAL haute confiance suffit
            if r.confidence >= 0.9:
                critical_weight += w  # double le poids
        elif r.level == AlertLevel.WARNING:
            warning_weight += w

    # Choisir le niveau final
    worst = max(candidates, key=lambda r: _SEVERITY[r.level])

    if critical_weight >= 2 * _WEIGHTS.get("rules", 2.0) or critical_weight >= 3.0:
        level = AlertLevel.CRITICAL
    elif (warning_weight + critical_weight) >= 2.0:
        level = AlertLevel.WARNING if worst.level == AlertLevel.WARNING else worst.level
    else:
        level = AlertLevel.NORMAL

    # Si le vote donne un niveau moins sévère que le pire individuel, garder le pire
    if _SEVERITY[worst.level] > _SEVERITY[level]:
        level = worst.level

    total_weight = sum(_WEIGHTS.get(r.method, 1.0) for r in candidates)
    conf = (critical_weight + warning_weight * 0.5) / total_weight if total_weight > 0 else 0.0
    conf = round(min(1.0, conf), 3)

    methods_fired = [r.method for r in candidates if r.level != AlertLevel.NORMAL]
    method_str = "ensemble[" + ",".join(methods_fired) + "]" if methods_fired else "ensemble"

    reasons = [r.reason for r in candidates if r.level != AlertLevel.NORMAL]
    reason = "; ".join(reasons) if reasons else worst.reason

    return DetectionResult(
        sensor=worst.sensor,
        value=worst.value,
        unit=worst.unit,
        level=level,
        method=method_str,
        reason=reason,
        timestamp=worst.timestamp,
        z_score=worst.z_score,
        expected_min=worst.expected_min,
        expected_max=worst.expected_max,
        confidence=conf,
    )


class AnomalyDetectionEngine:
    """
    Orchestre les 7 détecteurs et fusionne leurs résultats par vote pondéré.

    Usage:
        engine = AnomalyDetectionEngine()
        results = engine.analyze_batch(readings)
        for r in results:
            if r.is_anomaly():
                print(r)
    """

    def __init__(self, window_size: int = 30):
        self.rules      = RuleBasedDetector()
        self.zscore     = ZScoreDetector(window_size=window_size)
        self.iqr        = IQRDetector(window_size=window_size)
        self.iforest    = IsolationForestDetector(window_size=max(window_size * 3, 100))
        self.mv_iforest = MultivariateIsolationForestDetector()
        self.autoenc    = LinearAutoencoderDetector(window_size=20, n_components=3, retrain_every=50)
        self.cusum      = CUSUMDetector(window_size=40, k_factor=0.5, h_factor=5.0)

    def analyze(self, reading: SensorReading) -> DetectionResult:
        """Analyse une lecture et retourne le résultat du vote d'ensemble."""
        _detectors = [
            ("rules",      self.rules),
            ("zscore",     self.zscore),
            ("iqr",        self.iqr),
            ("iforest",    self.iforest),
            ("mv_iforest", self.mv_iforest),
            ("autoenc",    self.autoenc),
            ("cusum",      self.cusum),
        ]
        candidates = []
        for name, det in _detectors:
            try:
                candidates.append(det.analyze(reading))
            except Exception:
                # Détecteur en erreur → contribue NORMAL avec confiance nulle
                candidates.append(DetectionResult(
                    sensor=reading.sensor,
                    value=float(reading.value),
                    unit=getattr(reading, "unit", "?"),
                    level=AlertLevel.NORMAL,
                    method=name,
                    reason=f"{name}: erreur interne",
                    confidence=0.0,
                ))
        return _ensemble_vote(candidates)

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
