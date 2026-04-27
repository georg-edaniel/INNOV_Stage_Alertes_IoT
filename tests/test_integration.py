"""
test_integration.py
-------------------
Tests d'intégration : simulateur → détection → alertes → API.
Vérifie que le pipeline complet fonctionne de bout en bout.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.alerts.database import Base, get_db
from src.alerts.service import AlertService
from src.detection.engine import AnomalyDetectionEngine
from src.simulator.generator import IoTSimulator
from src.api.main import app


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Pipeline complet ───────────────────────────────────────────────────────

class TestPipelineComplet:

    def test_pipeline_normal(self, db):
        """Lecture normale → aucune alerte créée."""
        sim    = IoTSimulator(anomaly_probability=0.0, seed=42)
        engine = AnomalyDetectionEngine()
        svc    = AlertService(db)

        readings = sim.read_all()
        results  = engine.analyze_batch(readings)
        alerts   = svc.process_batch(results, readings)

        # Pas d'anomalie → pas d'alerte
        assert all(not r.is_anomaly() for r in results)
        assert len(alerts) == 0
        # Mais les logs sont bien créés
        logs = svc.get_logs()
        assert len(logs) == 3

    def test_pipeline_anomalie_cree_alerte(self, db):
        """Pic de température → alerte CRITICAL créée."""
        from src.simulator.generator import SensorReading
        from src.detection.levels import AlertLevel

        engine = AnomalyDetectionEngine()
        svc    = AlertService(db)

        # Injecter un pic critique
        reading = SensorReading("temperature", 99.0, "spike_high")
        result  = engine.analyze(reading)
        alert   = svc.process(result, reading)

        assert result.level == AlertLevel.CRITICAL
        assert alert is not None
        assert alert.level == "CRITICAL"
        assert alert.sensor == "temperature"

    def test_pipeline_deduplication(self, db):
        """Deux anomalies identiques consécutives → une seule alerte."""
        from src.simulator.generator import SensorReading

        engine = AnomalyDetectionEngine()
        svc    = AlertService(db)

        reading = SensorReading("temperature", 99.0, "spike_high")
        result  = engine.analyze(reading)

        a1 = svc.process(result, reading)
        a2 = svc.process(result, reading)

        assert a1.id == a2.id
        assert svc.get_stats()["total"] == 1

    def test_pipeline_resolution_auto(self, db):
        """Retour à la normale → alerte auto-résolue."""
        from src.simulator.generator import SensorReading
        from src.detection.levels import AlertLevel, DetectionResult

        svc = AlertService(db)

        # Alerte critique
        crit = DetectionResult("temperature", 99.0, "°C", AlertLevel.CRITICAL, "rules", "Test")
        alert = svc.process(crit)
        assert alert.resolved is False

        # Retour normal
        norm = DetectionResult("temperature", 20.0, "°C", AlertLevel.NORMAL, "rules", "OK")
        svc.process(norm)

        db.refresh(alert)
        assert alert.resolved is True

    def test_pipeline_multi_capteurs(self, db):
        """Anomalies sur plusieurs capteurs → alertes indépendantes."""
        from src.simulator.generator import SensorReading
        from src.detection.levels import AlertLevel, DetectionResult

        svc = AlertService(db)
        results = [
            DetectionResult("temperature", 99.0, "°C",   AlertLevel.CRITICAL, "rules", "Trop chaud"),
            DetectionResult("ph",          2.0,  "pH",   AlertLevel.CRITICAL, "rules", "pH acide"),
            DetectionResult("turbidity",   0.5,  "NTU",  AlertLevel.NORMAL,   "rules", "OK"),
        ]
        alerts = svc.process_batch(results)
        assert len(alerts) == 2
        sensors = {a.sensor for a in alerts}
        assert "temperature" in sensors
        assert "ph" in sensors


# ── API de bout en bout ────────────────────────────────────────────────────

class TestAPIEndToEnd:

    def test_tick_puis_liste_alertes(self, client):
        """POST /tick génère des données → GET /alerts retourne les alertes."""
        # Plusieurs ticks pour augmenter la probabilité d'anomalie
        for _ in range(10):
            client.post("/api/simulator/tick")

        r = client.get("/api/alerts")
        assert r.status_code == 200
        # Vérifier la structure de la réponse
        data = r.json()
        assert "alerts" in data
        assert "count" in data

    def test_tick_puis_logs(self, client):
        """Chaque tick crée 3 logs (un par capteur)."""
        client.post("/api/simulator/tick")
        r = client.get("/api/logs")
        assert r.status_code == 200
        assert r.json()["count"] >= 3

    def test_acknowledge_resolve_workflow(self, client):
        """Workflow complet : créer alerte → acquitter → résoudre."""
        # Forcer une alerte via tick
        for _ in range(20):
            r = client.post("/api/simulator/tick")
            if r.json()["alerts_created"]:
                alert_id = r.json()["alerts_created"][0]["id"]
                break
        else:
            pytest.skip("Aucune alerte générée (probabilité faible)")

        # Acquitter
        r = client.patch(f"/api/alerts/{alert_id}/acknowledge")
        assert r.status_code == 200
        assert r.json()["alert"]["acknowledged"] is True

        # Résoudre
        r = client.patch(f"/api/alerts/{alert_id}/resolve")
        assert r.status_code == 200
        assert r.json()["alert"]["resolved"] is True

    def test_filtre_par_niveau(self, client):
        """GET /api/alerts?level=CRITICAL retourne seulement les critiques."""
        for _ in range(15):
            client.post("/api/simulator/tick")

        r = client.get("/api/alerts?level=CRITICAL")
        assert r.status_code == 200
        for a in r.json()["alerts"]:
            assert a["level"] == "CRITICAL"

    def test_stats_coherentes(self, client):
        """Les stats total = warning + critical + (normaux résolus auto)."""
        for _ in range(5):
            client.post("/api/simulator/tick")

        r = client.get("/api/logs/stats")
        s = r.json()
        assert s["total"] >= 0
        assert s["resolved"] <= s["total"]
        assert s["critical"] + s["warning"] <= s["total"]

    def test_pages_html_accessibles(self, client):
        """Les pages HTML retournent HTTP 200."""
        for path in ["/", "/alerts", "/logs"]:
            r = client.get(path)
            assert r.status_code == 200, f"{path} → {r.status_code}"

    def test_health_ok(self, client):
        """GET /health retourne status ok."""
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
