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
    sensor:    str | None  = Query(None),
    level:     str | None  = Query(None),
    resolved:  bool | None = Query(None),
    date_from: str | None  = Query(None, description="ISO date YYYY-MM-DD"),
    date_to:   str | None  = Query(None, description="ISO date YYYY-MM-DD"),
    q:         str | None  = Query(None, description="Recherche dans la raison"),
    limit:  int = Query(50,  ge=1, le=200),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    """Liste les alertes avec filtres optionnels."""
    from datetime import datetime, timezone, timedelta
    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None
    svc    = AlertService(db)
    alerts = svc.get_all(
        sensor=sensor, level=level, resolved=resolved,
        date_from=df, date_to=dt, search=q,
        limit=limit, offset=offset,
    )
    total = svc.count_all(sensor=sensor, level=level, resolved=resolved, date_from=df, date_to=dt, search=q)
    return {"alerts": [a.to_dict() for a in alerts], "count": len(alerts), "total": total}


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


@alerts_router.patch("/{alert_id}/notes")
def update_note(alert_id: int, note: str = "", db: Session = Depends(get_db)):
    """Ajoute ou met à jour la note opérateur d'une alerte."""
    alert = AlertService(db).add_note(alert_id, note)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"message": "Note enregistrée", "alert": alert.to_dict()}


@alerts_router.patch("/{alert_id}/tags")
def update_tags(alert_id: int, tags: str = Query("", description="Tags séparés par virgules"), db: Session = Depends(get_db)):
    """Définit les tags d'une alerte."""
    tag_list = [t for t in tags.split(",") if t.strip()]
    alert = AlertService(db).set_tags(alert_id, tag_list)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"message": "Tags enregistrés", "alert": alert.to_dict()}


@alerts_router.delete("/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """Supprime définitivement une alerte."""
    deleted = AlertService(db).delete(alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"message": "Alerte supprimée"}


@alerts_router.delete("")
def delete_alerts_bulk(
    ids: str = Query(..., description="IDs séparés par virgules, ex: 1,2,3"),
    db: Session = Depends(get_db),
):
    """Supprime plusieurs alertes en une seule requête."""
    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="IDs invalides")
    count = AlertService(db).delete_bulk(id_list)
    return {"message": f"{count} alerte(s) supprimée(s)", "count": count}


@alerts_router.patch("/acknowledge-all")
def acknowledge_all(db: Session = Depends(get_db)):
    count = AlertService(db).acknowledge_all()
    return {"message": f"{count} alerte(s) acquittée(s)"}


@alerts_router.get("/export-json")
def export_alerts_json(
    sensor:   str | None  = Query(None),
    level:    str | None  = Query(None),
    resolved: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    """Exporte les alertes filtrées en JSON téléchargeable."""
    import json as _json
    svc    = AlertService(db)
    alerts = svc.get_all(sensor=sensor, level=level, resolved=resolved, limit=5000)
    payload = _json.dumps([a.to_dict() for a in alerts], indent=2, ensure_ascii=False)
    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=alertes.json"},
    )


@alerts_router.post("/archive")
def archive_alerts(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """Archive les alertes résolues de plus de N jours."""
    count = AlertService(db).archive_old_alerts(days=days)
    return {"message": f"{count} alerte(s) archivée(s)", "count": count}


# ── /api/logs ─────────────────────────────────────────────────────────────

@logs_router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Statistiques globales des alertes."""
    return AlertService(db).get_stats()


@logs_router.get("/mttr")
def get_mttr(db: Session = Depends(get_db)):
    """Mean Time To Resolve par capteur (secondes)."""
    return AlertService(db).get_mttr()


@logs_router.get("/heatmap")
def get_heatmap(days: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)):
    """Heatmap des anomalies par heure/jour sur les N derniers jours."""
    return AlertService(db).get_heatmap(days=days)


@logs_router.get("/correlation")
def get_correlation(days: int = Query(1, ge=1, le=30), db: Session = Depends(get_db)):
    """Paires de valeurs capteurs pour graphiques de corrélation."""
    return AlertService(db).get_correlation(days=days)


@logs_router.get("/open-duration")
def get_open_duration(days: int = Query(7, ge=1, le=30), db: Session = Depends(get_db)):
    """Durée moyenne des alertes non résolues par niveau."""
    return AlertService(db).get_open_duration(days=days)


@logs_router.get("/trend")
def get_trend(
    days:   int = Query(30, ge=1, le=90),
    sensor: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Agrégation journalière des lectures par capteur sur N jours."""
    return AlertService(db).get_trend(days=days, sensor=sensor)


@logs_router.get("/compare")
def get_comparison(
    period: str = Query("week", description="week | month"),
    db: Session = Depends(get_db),
):
    """Statistiques période courante vs période précédente."""
    if period not in ("week", "month"):
        from fastapi import HTTPException
        raise HTTPException(400, "period doit être 'week' ou 'month'")
    return AlertService(db).get_comparison(period=period)


@logs_router.get("/audit")
def get_audit(
    alert_id: int | None = Query(None),
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Journal d'audit des actions opérateur."""
    svc   = AlertService(db)
    logs  = svc.get_audit_log(alert_id=alert_id, limit=limit, offset=offset)
    total = svc.count_audit_log(alert_id=alert_id)
    return {"logs": [l.to_dict() for l in logs], "total": total}


@logs_router.get("")
def list_logs(
    sensor:    str | None = Query(None),
    date_from: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    date_to:   str | None = Query(None, description="ISO date YYYY-MM-DD"),
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
):
    """Historique des lectures capteurs."""
    from datetime import datetime, timezone, timedelta
    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None
    svc  = AlertService(db)
    logs = svc.get_logs(sensor=sensor, date_from=df, date_to=dt, limit=limit, offset=offset)
    total = svc.count_logs(sensor=sensor, date_from=df, date_to=dt)
    return {"logs": [l.to_dict() for l in logs], "count": len(logs), "total": total}


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


@simulator_router.get("/status")
def simulator_status():
    """Retourne l'état courant du simulateur (running ou non)."""
    from .main import get_scheduler
    s = get_scheduler()
    return {"running": s.is_running if s else False}


@simulator_router.post("/start")
def simulator_start():
    """Démarre le simulateur si arrêté."""
    from .main import get_scheduler
    s = get_scheduler()
    if not s:
        raise HTTPException(status_code=503, detail="Scheduler non initialisé")
    if s.is_running:
        return {"running": True, "message": "Déjà en cours"}
    s.start()
    return {"running": True, "message": "Simulateur démarré"}


@simulator_router.post("/stop")
def simulator_stop():
    """Arrête le simulateur si en cours."""
    from .main import get_scheduler
    s = get_scheduler()
    if not s:
        raise HTTPException(status_code=503, detail="Scheduler non initialisé")
    if not s.is_running:
        return {"running": False, "message": "Déjà arrêté"}
    s.stop()
    return {"running": False, "message": "Simulateur arrêté"}


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


@config_router.get("/thresholds/history")
def get_threshold_history(limit: int = Query(30, ge=1, le=100)):
    """Retourne l'historique des modifications de seuils."""
    from ..alerts.threshold_config import get_history
    return {"history": get_history(limit=limit)}


@config_router.get("/webhook")
def get_webhook():
    """Retourne la configuration webhook actuelle."""
    from ..alerts.notifier import get_config
    return get_config()


@config_router.post("/webhook")
def set_webhook(
    url:    str  = Query("", description="URL du webhook"),
    active: bool = Query(False),
    format: str  = Query("generic", description="generic | slack | discord"),
):
    """Configure le webhook de notification (alertes CRITICAL)."""
    from ..alerts.notifier import set_config
    return set_config(url=url, active=active, fmt=format)


@config_router.get("/email")
def get_email_config():
    """Retourne la configuration email SMTP (sans mot de passe)."""
    from ..alerts.email_notifier import get_config
    return get_config()


@config_router.post("/email")
def set_email_config(
    smtp_host: str  = Query("smtp.gmail.com"),
    smtp_port: int  = Query(587),
    username:  str  = Query(""),
    password:  str  = Query(""),
    from_addr: str  = Query(""),
    to_addr:   str  = Query(""),
    active:    bool = Query(False),
):
    """Configure la notification email SMTP."""
    from ..alerts.email_notifier import set_config
    return set_config(
        smtp_host=smtp_host, smtp_port=smtp_port,
        username=username, password=password if password != "***" else None,
        from_addr=from_addr, to_addr=to_addr, active=active,
    )
