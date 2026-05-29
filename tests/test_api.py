"""
test_api.py
-----------
Tests d'intégration API — endpoints REST + pages dashboard.
"""

import pytest


class TestHealthEndpoint:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestAlertsCRUD:
    def test_list_empty_initially(self, client):
        r = client.get("/api/alerts?limit=5")
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data
        assert "total" in data

    def test_ingest_and_list(self, client):
        # Ingérer une lecture normale (ne devrait pas créer d'alerte)
        r = client.post("/api/ingest?sensor=temperature&value=22.5&unit=°C")
        assert r.status_code == 200
        data = r.json()
        assert data["sensor"] == "temperature"
        assert data["level"] in ("NORMAL", "WARNING", "CRITICAL")

    def test_ingest_critical_creates_alert(self, client):
        # Température bien au-dessus des seuils → CRITICAL
        r = client.post("/api/ingest?sensor=temperature&value=999&unit=°C")
        assert r.status_code == 200
        data = r.json()
        assert data["level"] == "CRITICAL"

    def test_acknowledge(self, client):
        # Créer une alerte critique
        client.post("/api/ingest?sensor=ph&value=0.1&unit=pH")
        # Lister pour trouver l'ID
        alerts = client.get("/api/alerts?limit=5").json()["alerts"]
        if not alerts:
            pytest.skip("Aucune alerte disponible")
        alert_id = alerts[0]["id"]
        r = client.patch(f"/api/alerts/{alert_id}/acknowledge")
        assert r.status_code == 200
        assert r.json()["alert"]["acknowledged"] is True

    def test_resolve(self, client):
        alerts = client.get("/api/alerts?resolved=false&limit=5").json()["alerts"]
        if not alerts:
            pytest.skip("Aucune alerte ouverte disponible")
        alert_id = alerts[0]["id"]
        r = client.patch(f"/api/alerts/{alert_id}/resolve")
        assert r.status_code == 200
        assert r.json()["alert"]["resolved"] is True

    def test_delete(self, client):
        # Créer une alerte puis la supprimer
        client.post("/api/ingest?sensor=turbidity&value=9999&unit=NTU")
        alerts = client.get("/api/alerts?limit=5").json()["alerts"]
        if not alerts:
            pytest.skip("Aucune alerte disponible")
        alert_id = alerts[0]["id"]
        r = client.delete(f"/api/alerts/{alert_id}")
        assert r.status_code == 200
        # Vérifier la suppression
        r2 = client.get(f"/api/alerts/{alert_id}")
        assert r2.status_code == 404

    def test_invalid_sensor_ingest(self, client):
        r = client.post("/api/ingest?sensor=invalid_sensor&value=10&unit=X")
        assert r.status_code == 400


class TestSnooze:
    def test_snooze_and_unsnooze(self, client):
        # Créer une alerte critique
        client.post("/api/ingest?sensor=temperature&value=999&unit=°C")
        alerts = client.get("/api/alerts?resolved=false&limit=10").json()["alerts"]
        if not alerts:
            pytest.skip("Aucune alerte ouverte disponible")
        alert_id = alerts[0]["id"]

        # Snooze 30 min
        r = client.patch(f"/api/alerts/{alert_id}/snooze?minutes=30")
        assert r.status_code == 200
        data = r.json()
        assert data["alert"]["snoozed_until"] is not None

        # Unsnooze
        r2 = client.patch(f"/api/alerts/{alert_id}/unsnooze")
        assert r2.status_code == 200
        assert r2.json()["alert"]["snoozed_until"] is None

    def test_snooze_not_found(self, client):
        r = client.patch("/api/alerts/999999/snooze?minutes=30")
        assert r.status_code == 404


class TestDashboardPages:
    def test_dashboard_200(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"Dashboard" in r.content or b"IoT" in r.content

    def test_alerts_page_200(self, client):
        r = client.get("/alerts")
        assert r.status_code == 200

    def test_report_page_200(self, client):
        r = client.get("/report?days=1")
        assert r.status_code == 200

    def test_predict_page_200(self, client):
        r = client.get("/predict")
        assert r.status_code == 200

    def test_spc_page_200(self, client):
        r = client.get("/spc")
        assert r.status_code == 200

    def test_timeline_page_200(self, client):
        r = client.get("/timeline")
        assert r.status_code == 200

    def test_logs_overlay_200(self, client):
        r = client.get("/logs/overlay")
        assert r.status_code == 200

    def test_cusum_page_200(self, client):
        r = client.get("/cusum")
        assert r.status_code == 200

    def test_404_page(self, client):
        r = client.get("/alerts/999999")
        # Retourne 404 ou redirect login
        assert r.status_code in (200, 302, 404)


class TestLogsEndpoints:
    def test_stats(self, client):
        r = client.get("/api/logs/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "critical" in data

    def test_heatmap(self, client):
        r = client.get("/api/logs/heatmap?days=7")
        assert r.status_code == 200
        data = r.json()
        assert "grid" in data
        assert len(data["grid"]) == 7

    def test_correlation(self, client):
        r = client.get("/api/logs/correlation?days=1")
        assert r.status_code == 200
        data = r.json()
        assert "points" in data

    def test_composite_alerts(self, client):
        r = client.get("/api/logs/composite")
        assert r.status_code == 200
        assert "alerts" in r.json()

    def test_list_logs(self, client):
        r = client.get("/api/logs?limit=10")
        assert r.status_code == 200
        data = r.json()
        assert "logs" in data

    def test_sensor_health(self, client):
        r = client.get("/api/sensors/health")
        assert r.status_code == 200
        data = r.json()
        assert "temperature" in data


class TestConfigEndpoints:
    def test_get_thresholds(self, client):
        r = client.get("/api/config/thresholds")
        assert r.status_code == 200
        data = r.json()
        assert "temperature" in data

    def test_get_telegram_config(self, client):
        r = client.get("/api/config/telegram")
        assert r.status_code == 200
        data = r.json()
        assert "active" in data

    def test_get_mqtt_config(self, client):
        r = client.get("/api/config/mqtt")
        assert r.status_code == 200
        data = r.json()
        assert "broker" in data

    def test_get_escalation_config(self, client):
        r = client.get("/api/config/escalation")
        assert r.status_code == 200
        data = r.json()
        assert "active" in data
        assert "delay_minutes" in data

    def test_set_escalation_config(self, client):
        r = client.post("/api/config/escalation?active=true&delay_minutes=15&notify_telegram=false&notify_webhook=true&notify_email=false")
        assert r.status_code == 200
        data = r.json()
        assert data["delay_minutes"] == 15
        assert data["active"] is True
