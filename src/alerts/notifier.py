"""
notifier.py
-----------
Service de notifications webhook (Slack / Discord / générique).
Déclenché sur chaque alerte CRITICAL créée.
Configuration persistée dans webhook_config.json.
"""

import json
import logging
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent.parent.parent / "webhook_config.json"

_DEFAULT = {"url": "", "active": False, "format": "generic"}


def _load() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_DEFAULT)


def _save(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_config() -> dict:
    return _load()


def set_config(url: str, active: bool, fmt: str = "generic") -> dict:
    cfg = {"url": url.strip(), "active": active, "format": fmt}
    _save(cfg)
    return cfg


def _build_payload(alert: dict, fmt: str) -> dict:
    ts  = alert.get("created_at", datetime.now(timezone.utc).isoformat())
    msg = (
        f"🚨 Alerte {alert['level']} — {alert['sensor']}\n"
        f"Valeur : {alert['value']} {alert.get('unit','')}\n"
        f"Raison : {alert['reason']}\n"
        f"Horodatage : {ts}"
    )
    if fmt == "slack":
        return {"text": msg}
    if fmt == "discord":
        return {"content": msg}
    return {
        "level":     alert["level"],
        "sensor":    alert["sensor"],
        "value":     alert["value"],
        "unit":      alert.get("unit", ""),
        "reason":    alert["reason"],
        "timestamp": ts,
        "message":   msg,
    }


def _send(url: str, payload: dict):
    try:
        data = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info("Webhook envoyé → %s (HTTP %s)", url, resp.status)
    except Exception as e:
        logger.warning("Webhook échoué : %s", e)


def notify(alert: dict):
    """Envoie une notification webhook si activée et si alerte CRITICAL."""
    if alert.get("level") != "CRITICAL":
        return
    cfg = _load()
    if not cfg.get("active") or not cfg.get("url"):
        return
    payload = _build_payload(alert, cfg.get("format", "generic"))
    # Envoi en arrière-plan pour ne pas bloquer la requête
    threading.Thread(target=_send, args=(cfg["url"], payload), daemon=True).start()
