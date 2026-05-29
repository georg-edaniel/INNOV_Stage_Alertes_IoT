"""
telegram_notifier.py
--------------------
Notification via bot Telegram lors d'alertes CRITICAL (ou WARNING si configuré).
Configuration stockée dans telegram_config.json.
"""

import json
import threading
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent.parent / "telegram_config.json"

_DEFAULT = {
    "active":    False,
    "bot_token": "",
    "chat_id":   "",
    "min_level": "CRITICAL",  # CRITICAL | WARNING
}


def _load() -> dict:
    if CONFIG_FILE.exists():
        try:
            return {**_DEFAULT, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(_DEFAULT)


def get_config() -> dict:
    cfg  = _load()
    safe = dict(cfg)
    if safe.get("bot_token"):
        safe["bot_token"] = safe["bot_token"][:6] + "***"
    return safe


def set_config(**kwargs) -> dict:
    cfg = _load()
    for k, v in kwargs.items():
        if k in cfg and v is not None:
            cfg[k] = v
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_config()


def _send(alert: dict, cfg: dict):
    try:
        import urllib.request
        import urllib.parse

        level  = alert.get("level", "UNKNOWN")
        sensor = alert.get("sensor", "?")
        value  = alert.get("value", "?")
        unit   = alert.get("unit", "")
        reason = alert.get("reason", "")
        ts     = (alert.get("created_at") or "")[:19].replace("T", " ")

        icon = "🚨" if level == "CRITICAL" else "⚠️"
        text = (
            f"{icon} *{level}* — {sensor}\n"
            f"Valeur: {value} {unit}\n"
            f"Raison: {reason}\n"
            f"Heure: {ts} UTC\n"
            f"_Système IoT — INNOV/CCNB 2026_"
        )

        url  = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id":    cfg["chat_id"],
            "text":       text,
            "parse_mode": "Markdown",
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


def notify(alert: dict):
    """Envoie une notification Telegram si configurée et active."""
    cfg       = _load()
    min_level = cfg.get("min_level", "CRITICAL")
    level     = alert.get("level", "NORMAL")

    _LEVELS = {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}
    if _LEVELS.get(level, 0) < _LEVELS.get(min_level, 2):
        return
    if not cfg.get("active") or not cfg.get("bot_token") or not cfg.get("chat_id"):
        return
    threading.Thread(target=_send, args=(alert, cfg), daemon=True).start()
