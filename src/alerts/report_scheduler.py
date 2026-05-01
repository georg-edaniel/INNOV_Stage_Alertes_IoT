"""
report_scheduler.py
-------------------
Configuration et envoi automatique du rapport périodique par email.
Config stockée dans report_schedule_config.json.
"""

import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent.parent / "report_schedule_config.json"

_DEFAULT = {
    "active":      False,
    "frequency":   "daily",    # daily | weekly
    "hour":        8,           # heure d'envoi (0-23)
    "days_period": 1,           # période du rapport (1 | 7 | 30)
}


def load_report_schedule() -> dict:
    if CONFIG_FILE.exists():
        try:
            return {**_DEFAULT, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(_DEFAULT)


def save_report_schedule(**kwargs) -> dict:
    cfg = load_report_schedule()
    for k, v in kwargs.items():
        if k in cfg and v is not None:
            cfg[k] = v
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def send_scheduled_report(db_factory):
    """Appelée par le scheduler — envoie le rapport si configuré."""
    from datetime import datetime, timezone
    cfg = load_report_schedule()
    if not cfg.get("active"):
        return

    # Vérifier l'heure
    now = datetime.now(timezone.utc)
    if now.hour != cfg.get("hour", 8):
        return

    # Vérifier le jour (weekly = uniquement lundi)
    if cfg.get("frequency") == "weekly" and now.weekday() != 0:
        return

    db = db_factory()
    try:
        from .service import AlertService
        from .email_notifier import send_report
        svc  = AlertService(db)
        days = cfg.get("days_period", 1)
        data = svc.get_report_data(days=days)
        send_report(data, days)
    except Exception:
        pass
    finally:
        db.close()
