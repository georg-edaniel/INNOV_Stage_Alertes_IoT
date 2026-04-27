"""
routers.py
----------
Tous les endpoints REST de l'application.

Alertes   : GET /api/alerts, GET /api/alerts/{id}, PATCH ack/resolve, GET /api/alerts/export
Logs      : GET /api/logs, GET /api/logs/stats, GET /api/logs/mttr
Capteurs  : GET /api/sensors/health
Simulateur: POST /api/simulator/tick, POST /api/simulator/config
Config    : GET/POST /api/config/thresholds, POST /api/config/thresholds/reset
"""

import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..alerts.database import get_db
from ..alerts.service import AlertService
from ..detection.engine import AnomalyDetectionEngine
from ..simulator.generator import IoTSimulator

# Instances partagées (state simple, suffisant pour ce projet)
_simulator = IoTSimulator(anomaly_probability=0.20)
_engine    = AnomalyDetectionEngine(window_size=30)

alerts_router    = APIRouter()
logs_router      = APIRouter()
sensors_router   = APIRouter()
simulator_router = APIRouter()
config_router    = APIRouter()


# ── /api/alerts ────────────────────────────────────────────────────────────

@alerts_router.get("/export")
def export_alerts_csv(
    sensor:   str | None  = Query(None),
    level:    str | None  = Query(None),
    resolved: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    """Exporte les alertes filtrées en CSV téléchargeable."""
    svc    = AlertService(db)
    alerts = svc.get_all(sensor=sensor, level=level, resolved=resolved, limit=5000)

    output = io.StringIO()
    fieldnames = ["id", "sensor", "value", "unit", "level", "method", "reason",
                  "z_score", "acknowledged", "resolved", "created_at", "resolved_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for a in alerts:
        writer.writerow(a.to_dict())

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=alertes.csv"},
    )


@alerts_router.get("")
def list_alerts(
    sensor:   str | None  = Query(None),
    level:    str | None  = Query(None),
    resolved: bool | None = Query(None),
    limit:  int = Query(50,  ge=1, le=200),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    """Liste les alertes avec filtres optionnels."""
    svc    = AlertService(db)
    alerts = svc.get_all(sensor=sensor, level=level, resolved=resolved, limit=limit, offset=offset)
    return {"alerts": [a.to_dict() for a in alerts], "count": len(alerts)}


@alerts_router.get("/open")
def open_alerts_count(db: Session = Depends(get_db)):
    """Nombre d'alertes ouvertes par niveau."""
    return AlertService(db).get_open_count()


@alerts_router.get("/{alert_id}")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """Détail d'une alerte."""
    alert = AlertService(db).get_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return alert.to_dict()


@alerts_router.patch("/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = AlertService(db).acknowledge(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"message": "Alerte acquittée", "alert": alert.to_dict()}


@alerts_router.patch("/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = AlertService(db).resolve(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"message": "Alerte résolue", "alert": alert.to_dict()}


@alerts_router.patch("/acknowledge-all")
def acknowledge_all(db: Session = Depends(get_db)):
    count = AlertService(db).acknowledge_all()
    return {"message": f"{count} alerte(s) acquittée(s)"}


# ── /api/logs ─────────────────────────────────────────────────────────────

@logs_router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Statistiques globales des alertes."""
    return AlertService(db).get_stats()


@logs_router.get("/mttr")
def get_mttr(db: Session = Depends(get_db)):
    """Mean Time To Resolve par capteur (secondes)."""
    return AlertService(db).get_mttr()


@logs_router.get("")
def list_logs(
    sensor: str | None = Query(None),
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    """Historique des lectures capteurs."""
    logs = AlertService(db).get_logs(sensor=sensor, limit=limit, offset=offset)
    return {"logs": [l.to_dict() for l in logs], "count": len(logs)}


# ── /api/sensors ──────────────────────────────────────────────────────────

@sensors_router.get("/health")
def sensor_health(db: Session = Depends(get_db)):
    """Dernier état connu (niveau + valeur) pour chaque capteur."""
    return AlertService(db).get_sensor_health()


# ── /api/simulator ────────────────────────────────────────────────────────

@simulator_router.post("/tick")
def simulator_tick(db: Session = Depends(get_db)):
    """Déclenche manuellement un cycle complet (3 capteurs)."""
    readings = _simulator.read_all()
    results  = _engine.analyze_batch(readings)
    svc      = AlertService(db)
    alerts   = svc.process_batch(results, readings)
    return {
        "readings":       [r.to_dict() for r in readings],
        "results":        [r.to_dict() for r in results],
        "alerts_created": [a.to_dict() for a in alerts],
    }


@simulator_router.post("/tick/{sensor}")
def simulator_tick_sensor(sensor: str, db: Session = Depends(get_db)):
    """Déclenche un cycle pour un seul capteur."""
    try:
        reading = _simulator.read_sensor(sensor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = _engine.analyze(reading)
    svc    = AlertService(db)
    alert  = svc.process(result, reading)
    return {
        "reading": reading.to_dict(),
        "result":  result.to_dict(),
        "alert":   alert.to_dict() if alert else None,
    }


@simulator_router.post("/config")
def set_simulator_config(
    probability: float = Query(0.20, ge=0.0, le=1.0, description="Probabilité d'anomalie (0–1)"),
):
    """Modifie la probabilité d'anomalie du simulateur (en temps réel)."""
    from .stream import set_simulator_probability
    _simulator.anomaly_probability = probability
    set_simulator_probability(probability)   # synchronise aussi le simulateur SSE
    return {"anomaly_probability": probability}


# ── /api/config ───────────────────────────────────────────────────────────

@config_router.get("/thresholds")
def get_thresholds():
    """Retourne la configuration complète des seuils (base + overrides)."""
    from ..alerts.threshold_config import get_all
    return get_all()


@config_router.post("/thresholds")
def update_threshold(
    sensor:  str   = Query(..., description="temperature | turbidity | ph"),
    zone:    str   = Query(..., description="normal | warning | critical"),
    min_val: float | None = Query(None, alias="min"),
    max_val: float | None = Query(None, alias="max"),
):
    """Met à jour un seuil pour un capteur et une zone donnés."""
    from ..alerts.threshold_config import update_sensor
    if sensor not in ("temperature", "turbidity", "ph"):
        raise HTTPException(400, "Capteur invalide")
    if zone not in ("normal", "warning", "critical"):
        raise HTTPException(400, "Zone invalide")
    return update_sensor(sensor, zone, min_val, max_val)


@config_router.post("/thresholds/reset")
def reset_thresholds():
    """Réinitialise tous les seuils aux valeurs par défaut."""
    from ..alerts.threshold_config import reset_all
    reset_all()
    return {"message": "Seuils réinitialisés aux valeurs par défaut"}
