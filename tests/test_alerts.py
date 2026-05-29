"""Tests du module d'alertes (service + API)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.alerts.database import Base, get_db
from src.alerts.models import Alert, SensorLog
from src.alerts.service import AlertService, DEDUP_WINDOW_SECONDS
from src.detection.levels import AlertLevel, DetectionResult
from src.simulator.generator import SensorReading
from src.api.main import app


# ── Fixtures DB en mémoire ─────────────────────────────────────────────────

@pytest.fixture
def db():
    # StaticPool : toutes les connexions partagent le même objet SQLite en mémoire
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def svc(db):
    return AlertService(db)


def make_result(sensor="temperature", value=50.0, level=AlertLevel.CRITICAL, method="rules"):
    return DetectionResult(
        sensor=sensor, value=value, unit="°C",
        level=level, method=method, reason="Test alerte",
    )


def make_reading(sensor="temperature", value=50.0):
    return SensorReading(sensor=sensor, value=value, scenario="spike_high")


# ── AlertService ───────────────────────────────────────────────────────────

class TestAlertService:

    def test_normal_ne_cree_pas_alerte(self, svc):
        result = make_result(level=AlertLevel.NORMAL, value=20.0)
        alert  = svc.process(result)
        assert alert is None

    def test_critical_cree_alerte(self, svc):
        result = make_result(level=AlertLevel.CRITICAL)
        alert  = svc.process(result)
        assert alert is not None
        assert alert.level == "CRITICAL"
        assert alert.sensor == "temperature"

    def test_warning_cree_alerte(self, svc):
        result = make_result(level=AlertLevel.WARNING, value=33.0)
        alert  = svc.process(result)
        assert alert is not None
        assert alert.level == "WARNING"

    def test_deduplication_meme_alerte(self, svc):
        result = make_result(level=AlertLevel.CRITICAL)
        a1 = svc.process(result)
        a2 = svc.process(result)
        assert a1.id == a2.id  # même alerte retournée

    def test_log_cree_a_chaque_lecture(self, svc, db):
        result = make_result(level=AlertLevel.NORMAL, value=20.0)
        svc.process(result)
        svc.process(result)
        logs = db.query(SensorLog).all()
        assert len(logs) == 2

    def test_normal_auto_resolve_alerte_ouverte(self, svc, db):
        # Créer une alerte ouverte
        critical = make_result(level=AlertLevel.CRITICAL)
        alert    = svc.process(critical)
        assert alert.resolved is False

        # Retour à la normale → auto-résolution
        normal = make_result(level=AlertLevel.NORMAL, value=20.0)
        svc.process(normal)

        db.refresh(alert)
        assert alert.resolved is True

    def test_acknowledge(self, svc, db):
        alert = svc.process(make_result(level=AlertLevel.WARNING, value=33.0))
        assert alert.acknowledged is False
        svc.acknowledge(alert.id)
        db.refresh(alert)
        assert alert.acknowledged is True

    def test_resolve(self, svc, db):
        alert = svc.process(make_result(level=AlertLevel.CRITICAL))
        svc.resolve(alert.id)
        db.refresh(alert)
        assert alert.resolved is True
        assert alert.resolved_at is not None

    def test_get_all_filtre_par_sensor(self, svc):
        svc.process(make_result(sensor="temperature", level=AlertLevel.CRITICAL))
        svc.process(make_result(sensor="ph",          level=AlertLevel.WARNING, value=3.0, method="rules"))
        alerts = svc.get_all(sensor="temperature")
        assert all(a.sensor == "temperature" for a in alerts)

    def test_get_open_count(self, svc):
        svc.process(make_result(level=AlertLevel.CRITICAL))
        svc.process(make_result(sensor="ph", level=AlertLevel.WARNING, value=3.0, method="rules"))
        counts = svc.get_open_count()
        assert counts["critical"] >= 1
        assert counts["warning"]  >= 1

    def test_stats(self, svc):
        svc.process(make_result(level=AlertLevel.CRITICAL))
        stats = svc.get_stats()
        assert stats["total"]    >= 1
        assert stats["critical"] >= 1
        assert "open" in stats

    def test_process_batch(self, svc):
        results = [
            make_result(sensor="temperature", level=AlertLevel.CRITICAL),
            make_result(sensor="ph",          level=AlertLevel.NORMAL, value=7.0),
            make_result(sensor="turbidity",   level=AlertLevel.WARNING, value=7.0),
        ]
        alerts = svc.process_batch(results)
        assert len(alerts) == 2  # NORMAL ne crée pas d'alerte


# ── API FastAPI ────────────────────────────────────────────────────────────

@pytest.fixture
def client(db):
    """Client de test avec base de données isolée et auth désactivée."""
    from unittest.mock import patch
    app.dependency_overrides[get_db] = lambda: db
    with patch("src.api.auth.is_auth_enabled", return_value=False):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    app.dependency_overrides.clear()


class TestAPI:

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_simulator_tick(self, client):
        r = client.post("/api/simulator/tick")
        assert r.status_code == 200
        data = r.json()
        assert "readings" in data
        assert len(data["readings"]) == 3

    def test_simulator_tick_sensor(self, client):
        r = client.post("/api/simulator/tick/temperature")
        assert r.status_code == 200
        assert r.json()["reading"]["sensor"] == "temperature"

    def test_simulator_tick_sensor_inconnu(self, client):
        r = client.post("/api/simulator/tick/oxygene")
        assert r.status_code == 400

    def test_list_alerts_vide(self, client):
        r = client.get("/api/alerts")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_list_logs(self, client):
        client.post("/api/simulator/tick")
        r = client.get("/api/logs")
        assert r.status_code == 200
        assert r.json()["count"] >= 3

    def test_get_stats(self, client):
        r = client.get("/api/logs/stats")
        assert r.status_code == 200
        assert "total" in r.json()

    def test_get_alert_inexistante(self, client):
        r = client.get("/api/alerts/9999")
        assert r.status_code == 404

    def test_open_alerts_count(self, client):
        r = client.get("/api/alerts/open")
        assert r.status_code == 200
        data = r.json()
        assert "warning" in data and "critical" in data
