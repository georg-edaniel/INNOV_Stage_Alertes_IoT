"""Tests du moteur de détection d'anomalies."""

import pytest
from src.simulator.generator import SensorReading
from src.detection.levels import AlertLevel
from src.detection.rules import RuleBasedDetector
from src.detection.statistical import ZScoreDetector, IQRDetector
from src.detection.engine import AnomalyDetectionEngine


# ── Helpers ────────────────────────────────────────────────────────────────

def make_reading(sensor: str, value: float, scenario: str = "normal") -> SensorReading:
    return SensorReading(sensor=sensor, value=value, scenario=scenario)


# ── RuleBasedDetector ──────────────────────────────────────────────────────

class TestRuleBasedDetector:
    def setup_method(self):
        self.det = RuleBasedDetector()

    def test_temperature_normale(self):
        r = self.det.analyze(make_reading("temperature", 20.0))
        assert r.level == AlertLevel.NORMAL

    def test_temperature_warning_haute(self):
        r = self.det.analyze(make_reading("temperature", 33.0))
        assert r.level == AlertLevel.WARNING

    def test_temperature_critique_haute(self):
        r = self.det.analyze(make_reading("temperature", 50.0))
        assert r.level == AlertLevel.CRITICAL

    def test_ph_normale(self):
        r = self.det.analyze(make_reading("ph", 7.0))
        assert r.level == AlertLevel.NORMAL

    def test_ph_critique_bas(self):
        r = self.det.analyze(make_reading("ph", 3.0))
        assert r.level == AlertLevel.CRITICAL

    def test_turbidite_warning(self):
        r = self.det.analyze(make_reading("turbidity", 7.0))
        assert r.level == AlertLevel.WARNING

    def test_batch_retourne_bonne_taille(self):
        readings = [make_reading("temperature", v) for v in [10, 20, 50]]
        results  = self.det.analyze_batch(readings)
        assert len(results) == 3

    def test_to_dict_complet(self):
        r = self.det.analyze(make_reading("ph", 7.0))
        d = r.to_dict()
        assert d["level"] == "NORMAL"
        assert d["method"] == "rules"
        assert "reason" in d


# ── ZScoreDetector ─────────────────────────────────────────────────────────

class TestZScoreDetector:
    def setup_method(self):
        self.det = ZScoreDetector(window_size=20, warning_threshold=2.0, critical_threshold=3.0)

    def _feed_normal(self, sensor: str, n: int = 20, value: float = 20.0):
        for _ in range(n):
            self.det.analyze(make_reading(sensor, value))

    def test_initialisation_retourne_normal(self):
        r = self.det.analyze(make_reading("temperature", 20.0))
        assert r.level == AlertLevel.NORMAL
        assert "Initialisation" in r.reason

    def test_valeur_normale_apres_fenetre(self):
        self._feed_normal("temperature", 20)
        r = self.det.analyze(make_reading("temperature", 20.5))
        assert r.level == AlertLevel.NORMAL

    def test_spike_detecte_comme_anomalie(self):
        self._feed_normal("temperature", 20, value=20.0)
        r = self.det.analyze(make_reading("temperature", 200.0))
        assert r.level in (AlertLevel.WARNING, AlertLevel.CRITICAL)
        assert r.z_score is not None

    def test_reset_vide_fenetre(self):
        self._feed_normal("temperature", 20)
        self.det.reset("temperature")
        r = self.det.analyze(make_reading("temperature", 20.0))
        assert "Initialisation" in r.reason


# ── IQRDetector ────────────────────────────────────────────────────────────

class TestIQRDetector:
    def setup_method(self):
        self.det = IQRDetector(window_size=20)

    def _feed_normal(self, sensor: str, n: int = 20, value: float = 20.0):
        for _ in range(n):
            self.det.analyze(make_reading(sensor, value))

    def test_initialisation_retourne_normal(self):
        r = self.det.analyze(make_reading("ph", 7.0))
        assert r.level == AlertLevel.NORMAL

    def test_valeur_normale_apres_fenetre(self):
        self._feed_normal("ph", 20, value=7.0)
        r = self.det.analyze(make_reading("ph", 7.1))
        assert r.level == AlertLevel.NORMAL

    def test_outlier_detecte(self):
        self._feed_normal("ph", 20, value=7.0)
        r = self.det.analyze(make_reading("ph", 50.0))
        assert r.level in (AlertLevel.WARNING, AlertLevel.CRITICAL)


# ── AnomalyDetectionEngine ─────────────────────────────────────────────────

class TestAnomalyDetectionEngine:
    def setup_method(self):
        self.engine = AnomalyDetectionEngine(window_size=20)

    def test_critique_gagne_sur_normal(self):
        # Température très haute : rules = CRITICAL
        r = self.engine.analyze(make_reading("temperature", 99.0))
        assert r.level == AlertLevel.CRITICAL

    def test_analyse_batch(self):
        readings = [
            make_reading("temperature", 20.0),
            make_reading("turbidity",   1.0),
            make_reading("ph",          7.0),
        ]
        results = self.engine.analyze_batch(readings)
        assert len(results) == 3

    def test_summary_compte_bonne_anomalie(self):
        readings = [
            make_reading("temperature", 20.0),  # normal
            make_reading("temperature", 99.0),  # critical
            make_reading("temperature", 33.0),  # warning
        ]
        results = self.engine.analyze_batch(readings)
        s = self.engine.summary(results)
        assert s["total"] == 3
        assert s["critical"] >= 1
        assert 0 <= s["anomaly_rate"] <= 1

    def test_is_anomaly(self):
        r = self.engine.analyze(make_reading("temperature", 99.0))
        assert r.is_anomaly() is True

        r2 = self.engine.analyze(make_reading("temperature", 20.0))
        # Peut être NORMAL selon la fenêtre statistique
        assert isinstance(r2.is_anomaly(), bool)
