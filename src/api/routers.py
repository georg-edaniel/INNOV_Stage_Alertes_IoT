"""
routers.py
----------
Tous les endpoints REST de l'application.

Alertes   : GET /api/alerts, GET /api/alerts/{id}, PATCH ack/resolve
Logs      : GET /api/logs, GET /api/stats
Simulateur: POST /api/simulator/tick (déclenche une lecture manuelle)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
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
simulator_router = APIRouter()


# ── /api/alerts ────────────────────────────────────────────────────────────

@alerts_router.get("")
def list_alerts(
    sensor:   str | None = Query(None, description="Filtrer par capteur"),
    level:    str | None = Query(None, description="NORMAL | WARNING | CRITICAL"),
    resolved: bool | None = Query(None, description="True = résolues, False = ouvertes"),
    limit:  int = Query(50,  ge=1, le=200),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    """Liste les alertes avec filtres optionnels."""
    svc = AlertService(db)
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
    """Marque une alerte comme vue."""
    alert = AlertService(db).acknowledge(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"message": "Alerte acquittée", "alert": alert.to_dict()}


@alerts_router.patch("/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Marque une alerte comme résolue."""
    alert = AlertService(db).resolve(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"message": "Alerte résolue", "alert": alert.to_dict()}


@alerts_router.patch("/acknowledge-all")
def acknowledge_all(db: Session = Depends(get_db)):
    """Acquitte toutes les alertes ouvertes."""
    count = AlertService(db).acknowledge_all()
    return {"message": f"{count} alerte(s) acquittée(s)"}


# ── /api/logs ─────────────────────────────────────────────────────────────

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


@logs_router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Statistiques globales des alertes."""
    return AlertService(db).get_stats()


# ── /api/simulator ────────────────────────────────────────────────────────

@simulator_router.post("/tick")
def simulator_tick(db: Session = Depends(get_db)):
    """
    Déclenche manuellement un cycle du simulateur :
    génère 3 lectures (temp, turbidité, pH), les analyse et crée les alertes.
    """
    readings = _simulator.read_all()
    results  = _engine.analyze_batch(readings)
    svc      = AlertService(db)
    alerts   = svc.process_batch(results, readings)

    return {
        "readings": [r.to_dict() for r in readings],
        "results":  [r.to_dict() for r in results],
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
