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


@dashboard_router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Page principale du dashboard."""
    svc    = AlertService(db)
    stats  = svc.get_stats()
    open_c = svc.get_open_count()
    recent = svc.get_all(resolved=False, limit=10)
    return templates.TemplateResponse(request, "dashboard.html", {
        "stats":         stats,
        "open":          open_c,
        "recent_alerts": [a.to_dict() for a in recent],
    })


@dashboard_router.get("/alerts", response_class=HTMLResponse)
def alerts_page(
    request: Request,
    sensor:   str | None = None,
    level:    str | None = None,
    resolved: bool | None = None,
    db: Session = Depends(get_db),
):
    """Page historique des alertes avec filtres."""
    svc    = AlertService(db)
    alerts = svc.get_all(sensor=sensor, level=level, resolved=resolved, limit=100)
    stats  = svc.get_stats()
    return templates.TemplateResponse(request, "alerts.html", {
        "alerts":  [a.to_dict() for a in alerts],
        "stats":   stats,
        "filters": {"sensor": sensor, "level": level, "resolved": resolved},
    })


@dashboard_router.get("/logs", response_class=HTMLResponse)
def logs_page(
    request: Request,
    sensor: str | None = None,
    db: Session = Depends(get_db),
):
    """Page historique des lectures capteurs + graphiques."""
    svc  = AlertService(db)
    logs = svc.get_logs(sensor=sensor, limit=200)
    return templates.TemplateResponse(request, "logs.html", {
        "logs":   [l.to_dict() for l in logs],
        "sensor": sensor,
    })
