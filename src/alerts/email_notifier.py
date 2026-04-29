"""
email_notifier.py
-----------------
Notification par email SMTP lors d'alertes CRITICAL.
Configuration stockée dans email_config.json.
"""

import json
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent.parent / "email_config.json"

_DEFAULT = {
    "active":    False,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "username":  "",
    "password":  "",
    "from_addr": "",
    "to_addr":   "",
}


def _load() -> dict:
    if CONFIG_FILE.exists():
        try:
            return {**_DEFAULT, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(_DEFAULT)


def get_config() -> dict:
    cfg = _load()
    safe = {k: v for k, v in cfg.items() if k != "password"}
    safe["password"] = "***" if cfg.get("password") else ""
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
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[CRITICAL] Alerte IoT — {alert['sensor'].upper()} : {alert['value']} {alert['unit']}"
        msg["From"]    = cfg["from_addr"] or cfg["username"]
        msg["To"]      = cfg["to_addr"]

        html = f"""
        <html><body style="font-family:sans-serif;color:#333;">
        <div style="border-left:4px solid #e74c3c;padding:1rem 1.5rem;background:#fff5f5;border-radius:4px;max-width:600px;">
          <h2 style="color:#e74c3c;margin-top:0;">Alerte CRITICAL — {alert['sensor'].upper()}</h2>
          <table style="border-collapse:collapse;width:100%;">
            <tr><td style="padding:.4rem;font-weight:600;width:140px;">Capteur</td><td>{alert['sensor']}</td></tr>
            <tr style="background:#f9f9f9;"><td style="padding:.4rem;font-weight:600;">Valeur</td><td>{alert['value']} {alert['unit']}</td></tr>
            <tr><td style="padding:.4rem;font-weight:600;">Méthode</td><td>{alert['method']}</td></tr>
            <tr style="background:#f9f9f9;"><td style="padding:.4rem;font-weight:600;">Raison</td><td>{alert['reason']}</td></tr>
            <tr><td style="padding:.4rem;font-weight:600;">Horodatage</td><td>{alert['created_at'][:19].replace('T',' ')}</td></tr>
          </table>
          <p style="margin-top:1rem;font-size:.85rem;color:#666;">
            Système d'alertes IoT — INNOV/CCNB 2026
          </p>
        </div>
        </body></html>
        """
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=10) as server:
            server.ehlo()
            server.starttls()
            if cfg.get("username") and cfg.get("password"):
                server.login(cfg["username"], cfg["password"])
            server.sendmail(msg["From"], cfg["to_addr"], msg.as_string())
    except Exception:
        pass


def notify(alert: dict):
    """Envoie un email si l'alerte est CRITICAL et que l'email est configuré et actif."""
    if alert.get("level") != "CRITICAL":
        return
    cfg = _load()
    if not cfg.get("active") or not cfg.get("to_addr"):
        return
    threading.Thread(target=_send, args=(alert, cfg), daemon=True).start()
