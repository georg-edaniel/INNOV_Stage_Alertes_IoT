"""
metrics.py
----------
Métriques Prometheus pour l'application IoT.

Exposées sur GET /metrics (format texte Prometheus).

Métriques :
  - iot_alerts_total{sensor, level}     — compteur d'alertes par capteur/niveau
  - iot_readings_total{sensor}          — compteur de lectures par capteur
  - iot_active_alerts{sensor}           — jauge alertes actives (non-résolues) par capteur
  - iot_detection_latency_seconds       — histogramme de latence du moteur de détection
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

metrics_router = APIRouter()

# ── Registre Prometheus ────────────────────────────────────────────────────

try:
    from prometheus_client import (
        Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry,
    )
    _registry = CollectorRegistry()

    ALERTS_TOTAL = Counter(
        "iot_alerts_total",
        "Nombre total d'alertes créées",
        ["sensor", "level"],
        registry=_registry,
    )
    READINGS_TOTAL = Counter(
        "iot_readings_total",
        "Nombre total de lectures capteurs",
        ["sensor"],
        registry=_registry,
    )
    ACTIVE_ALERTS = Gauge(
        "iot_active_alerts",
        "Alertes actives (non-résolues) par capteur",
        ["sensor"],
        registry=_registry,
    )
    DETECTION_LATENCY = Histogram(
        "iot_detection_latency_seconds",
        "Latence du moteur de détection",
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5],
        registry=_registry,
    )

    _prometheus_available = True
    logger.info("Prometheus client chargé")

except ImportError:
    _prometheus_available = False
    logger.warning("prometheus-client non disponible — /metrics désactivé")

    # Stubs pour éviter les erreurs d'import
    class _Stub:
        def labels(self, **_): return self
        def inc(self, *_): pass
        def set(self, *_): pass
        def observe(self, *_): pass
        def time(self): return _NullCtx()

    class _NullCtx:
        def __enter__(self): return self
        def __exit__(self, *_): pass

    ALERTS_TOTAL     = _Stub()
    READINGS_TOTAL   = _Stub()
    ACTIVE_ALERTS    = _Stub()
    DETECTION_LATENCY = _Stub()


def record_alert(sensor: str, level: str):
    """Incrémente le compteur d'alertes."""
    try:
        ALERTS_TOTAL.labels(sensor=sensor, level=level).inc()
    except Exception:
        pass


def record_reading(sensor: str):
    """Incrémente le compteur de lectures."""
    try:
        READINGS_TOTAL.labels(sensor=sensor).inc()
    except Exception:
        pass


def set_active_alerts(sensor: str, count: int):
    """Met à jour le nombre d'alertes actives."""
    try:
        ACTIVE_ALERTS.labels(sensor=sensor).set(count)
    except Exception:
        pass


def update_active_alerts_from_db(db):
    """Relit depuis la DB et met à jour les jauges."""
    try:
        from ..alerts.models import Alert
        from sqlalchemy import func
        rows = (
            db.query(Alert.sensor, func.count(Alert.id))
            .filter(Alert.resolved == False)
            .group_by(Alert.sensor)
            .all()
        )
        for sensor, count in rows:
            set_active_alerts(sensor, count)
    except Exception as e:
        logger.debug(f"update_active_alerts_from_db: {e}")


@metrics_router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    """Endpoint Prometheus — format texte standard."""
    if not _prometheus_available:
        return PlainTextResponse(
            "# prometheus-client non installé\n",
            status_code=503,
            media_type="text/plain",
        )
    try:
        output = generate_latest(_registry)
        return PlainTextResponse(output.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error(f"metrics error: {e}")
        return PlainTextResponse(f"# erreur: {e}\n", status_code=500)
