"""
dashboard.py
------------
Routes HTML du dashboard (pages rendues côté serveur avec Jinja2).
"""

from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..alerts.database import get_db
from ..alerts.service import AlertService

TEMPLATES_DIR = Path(__file__).parent.parent / "dashboard" / "templates"
templates     = Jinja2Templates(directory=str(TEMPLATES_DIR))

dashboard_router = APIRouter()

PER_PAGE      = 20   # alertes par page
LOGS_PER_PAGE = 15   # lectures par page


@dashboard_router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Page principale du dashboard."""
    svc    = AlertService(db)
    stats  = svc.get_stats()
    open_c = svc.get_open_count()
    recent = svc.get_all(resolved=False, limit=10)
    mttr   = svc.get_mttr()
    health = svc.get_sensor_health()
    last_t = svc.get_last_alert_time()
    return templates.TemplateResponse(request, "dashboard.html", {
        "stats":         stats,
        "open":          open_c,
        "recent_alerts": [a.to_dict() for a in recent],
        "mttr":          mttr,
        "health":        health,
        "last_alert_at": last_t,
    })


@dashboard_router.get("/alerts", response_class=HTMLResponse)
def alerts_page(
    request:  Request,
    sensor:   str | None = None,
    level:    str | None = None,
    resolved: str | None = None,
    page:     int = 1,
    db: Session = Depends(get_db),
):
    """Page historique des alertes avec filtres et pagination."""
    sensor_f   = sensor or None
    level_f    = level  or None
    resolved_f: bool | None = None
    if resolved == "true":
        resolved_f = True
    elif resolved == "false":
        resolved_f = False

    page   = max(1, page)
    offset = (page - 1) * PER_PAGE

    svc    = AlertService(db)
    alerts = svc.get_all(sensor=sensor_f, level=level_f, resolved=resolved_f,
                         limit=PER_PAGE, offset=offset)
    # Compte total pour la pagination
    total  = len(svc.get_all(sensor=sensor_f, level=level_f, resolved=resolved_f, limit=5000))
    stats  = svc.get_stats()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    return templates.TemplateResponse(request, "alerts.html", {
        "alerts":       [a.to_dict() for a in alerts],
        "stats":        stats,
        "filters":      {"sensor": sensor_f, "level": level_f, "resolved": resolved_f},
        "page":         page,
        "total_pages":  total_pages,
        "total":        total,
        "per_page":     PER_PAGE,
        "has_prev":     page > 1,
        "has_next":     page < total_pages,
    })


@dashboard_router.get("/alerts/{alert_id}", response_class=HTMLResponse)
def alert_detail(alert_id: int, request: Request, db: Session = Depends(get_db)):
    """Page de détail d'une alerte."""
    svc   = AlertService(db)
    alert = svc.get_by_id(alert_id)
    if not alert:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    logs = svc.get_logs(sensor=alert.sensor, limit=50)
    return templates.TemplateResponse(request, "alert_detail.html", {
        "alert": alert.to_dict(),
        "logs":  [l.to_dict() for l in logs],
    })


@dashboard_router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request: Request,
    sensor: str | None = None,
    page:   int = 1,
    db: Session = Depends(get_db),
):
    """Page historique des lectures capteurs + graphiques (15 par page)."""
    page   = max(1, page)
    offset = (page - 1) * LOGS_PER_PAGE

    svc   = AlertService(db)
    logs  = svc.get_logs(sensor=sensor or None, limit=LOGS_PER_PAGE, offset=offset)
    total = len(svc.get_logs(sensor=sensor or None, limit=10000))
    total_pages = max(1, (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE)

    # Données graphique : 60 dernières lectures pour le chart (indépendant de la page)
    chart_logs = svc.get_logs(sensor=sensor or None, limit=60)

    return templates.TemplateResponse(request, "logs.html", {
        "logs":        [l.to_dict() for l in logs],
        "chart_logs":  [l.to_dict() for l in chart_logs],
        "sensor":      sensor,
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
        "per_page":    LOGS_PER_PAGE,
    })


@dashboard_router.get("/report", response_class=HTMLResponse)
def report_page(
    request: Request,
    days: int = 1,
    db: Session = Depends(get_db),
):
    """Page de rapport agrégé (dernières N journées)."""
    svc    = AlertService(db)
    report = svc.get_report_data(days=max(1, min(days, 30)))
    return templates.TemplateResponse(request, "report.html", {
        "report": report,
        "days":   days,
    })


@dashboard_router.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    """Page de configuration des seuils."""
    from ..alerts.threshold_config import get_all
    return templates.TemplateResponse(request, "thresholds.html", {
        "thresholds": get_all(),
    })
