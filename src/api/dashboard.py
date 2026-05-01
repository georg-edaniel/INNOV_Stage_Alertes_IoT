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
    request:   Request,
    sensor:    str | None = None,
    level:     str | None = None,
    resolved:  str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    q:         str | None = None,
    page:      int = 1,
    db: Session = Depends(get_db),
):
    """Page historique des alertes avec filtres et pagination."""
    from datetime import datetime, timezone, timedelta
    sensor_f   = sensor or None
    level_f    = level  or None
    resolved_f: bool | None = None
    if resolved == "true":
        resolved_f = True
    elif resolved == "false":
        resolved_f = False

    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None

    page   = max(1, page)
    offset = (page - 1) * PER_PAGE

    svc    = AlertService(db)
    alerts = svc.get_all(
        sensor=sensor_f, level=level_f, resolved=resolved_f,
        date_from=df, date_to=dt, search=q,
        limit=PER_PAGE, offset=offset,
    )
    total = svc.count_all(sensor=sensor_f, level=level_f, resolved=resolved_f, date_from=df, date_to=dt, search=q)
    stats  = svc.get_stats()
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    return templates.TemplateResponse(request, "alerts.html", {
        "alerts":      [a.to_dict() for a in alerts],
        "stats":       stats,
        "filters":     {
            "sensor": sensor_f, "level": level_f, "resolved": resolved_f,
            "date_from": date_from, "date_to": date_to, "q": q,
        },
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "per_page":    PER_PAGE,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
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
    request:   Request,
    sensor:    str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    page:      int = 1,
    db: Session = Depends(get_db),
):
    """Page historique des lectures capteurs + graphiques (15 par page)."""
    from datetime import datetime, timezone, timedelta
    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None

    page   = max(1, page)
    offset = (page - 1) * LOGS_PER_PAGE

    svc   = AlertService(db)
    logs  = svc.get_logs(sensor=sensor or None, date_from=df, date_to=dt, limit=LOGS_PER_PAGE, offset=offset)
    total = svc.count_logs(sensor=sensor or None, date_from=df, date_to=dt)
    total_pages = max(1, (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE)

    # Données graphique : 60 dernières lectures pour le chart (indépendant de la page)
    chart_logs = svc.get_logs(sensor=sensor or None, date_from=df, date_to=dt, limit=60)

    return templates.TemplateResponse(request, "logs.html", {
        "logs":        [l.to_dict() for l in logs],
        "chart_logs":  [l.to_dict() for l in chart_logs],
        "sensor":      sensor,
        "date_from":   date_from,
        "date_to":     date_to,
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
def config_page(request: Request, db: Session = Depends(get_db)):
    """Page de configuration des seuils."""
    from ..alerts.threshold_config import get_all
    svc     = AlertService(db)
    windows = svc.get_maintenance_windows()
    return templates.TemplateResponse(request, "thresholds.html", {
        "thresholds": get_all(),
        "maintenance_windows": [w.to_dict() for w in windows],
    })


@dashboard_router.get("/audit", response_class=HTMLResponse)
def audit_page(
    request:   Request,
    action:    str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    page:      int = 1,
    db: Session = Depends(get_db),
):
    """Page journal d'audit des actions opérateur."""
    from datetime import datetime, timezone, timedelta
    PER = 30
    svc    = AlertService(db)
    page   = max(1, page)
    offset = (page - 1) * PER
    df = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc) if date_from else None
    dt = (datetime.fromisoformat(date_to) + timedelta(days=1)).replace(tzinfo=timezone.utc) if date_to else None
    logs   = svc.get_audit_log(action=action or None, date_from=df, date_to=dt, limit=PER, offset=offset)
    total  = svc.count_audit_log(action=action or None, date_from=df, date_to=dt)
    total_pages = max(1, (total + PER - 1) // PER)
    return templates.TemplateResponse(request, "audit.html", {
        "logs":        [l.to_dict() for l in logs],
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
        "filter_action":    action or "",
        "filter_date_from": date_from or "",
        "filter_date_to":   date_to or "",
    })


@dashboard_router.get("/archived", response_class=HTMLResponse)
def archived_page(request: Request, page: int = 1, db: Session = Depends(get_db)):
    """Page des alertes archivées."""
    PER = 20
    svc    = AlertService(db)
    page   = max(1, page)
    offset = (page - 1) * PER
    alerts = svc.get_archived(limit=PER, offset=offset)
    total  = svc.count_archived()
    total_pages = max(1, (total + PER - 1) // PER)
    return templates.TemplateResponse(request, "archived.html", {
        "alerts":      [a.to_dict() for a in alerts],
        "page":        page,
        "total_pages": total_pages,
        "total":       total,
        "has_prev":    page > 1,
        "has_next":    page < total_pages,
    })


@dashboard_router.get("/presentation", response_class=HTMLResponse)
def presentation_page(request: Request, db: Session = Depends(get_db)):
    """Mode présentation — affichage mural sans navigation."""
    svc   = AlertService(db)
    stats = svc.get_stats()
    open_c = svc.get_open_count()
    health = svc.get_sensor_health()
    return templates.TemplateResponse(request, "presentation.html", {
        "stats":  stats,
        "open":   open_c,
        "health": health,
    })
