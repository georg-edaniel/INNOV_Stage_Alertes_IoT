"""
locustfile.py
-------------
Tests de charge Locust pour le système d'alertes IoT.

Utilisation :
    locust -f locustfile.py --headless -u 10 -r 2 -t 30s --host http://localhost:8084
    locust -f locustfile.py  (mode web, ouvrir http://localhost:8089)
"""

from locust import HttpUser, task, between


class DashboardUser(HttpUser):
    """Simule un utilisateur naviguant sur le dashboard."""
    wait_time = between(1, 3)

    @task(3)
    def dashboard(self):
        """Page principale — la plus fréquentée."""
        self.client.get("/", name="GET /")

    @task(2)
    def alerts(self):
        """Liste des alertes."""
        self.client.get("/alerts", name="GET /alerts")

    @task(2)
    def api_alerts(self):
        """API REST alertes."""
        self.client.get("/api/alerts?limit=20", name="GET /api/alerts")

    @task(1)
    def api_logs(self):
        """API REST historique."""
        self.client.get("/api/logs?limit=50", name="GET /api/logs")

    @task(1)
    def ingest(self):
        """Ingérer une lecture capteur."""
        self.client.post(
            "/api/ingest?sensor=temperature&value=22.5&unit=°C",
            name="POST /api/ingest",
        )

    @task(1)
    def health(self):
        """Health check."""
        self.client.get("/health", name="GET /health")

    @task(1)
    def sensor_health(self):
        """État des capteurs."""
        self.client.get("/api/sensors/health", name="GET /api/sensors/health")

    @task(1)
    def report(self):
        """Page rapport."""
        self.client.get("/report?days=1", name="GET /report")

    @task(1)
    def predict(self):
        """Page prédiction."""
        self.client.get("/predict", name="GET /predict")

    @task(1)
    def spc(self):
        """Page SPC."""
        self.client.get("/spc", name="GET /spc")

    @task(1)
    def stats(self):
        """Statistiques API."""
        self.client.get("/api/logs/stats", name="GET /api/logs/stats")
