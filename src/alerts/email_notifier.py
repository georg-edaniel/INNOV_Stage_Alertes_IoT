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


def _send_report(report_data: dict, days: int, cfg: dict):
    try:
        by_sensor = report_data.get("by_sensor", {})
        rows_html = ""
        for sensor, d in by_sensor.items():
            rows_html += f"""
            <tr>
              <td style="padding:.4rem .8rem;">{sensor}</td>
              <td style="padding:.4rem;text-align:center;">{d.get('total_alerts',0)}</td>
              <td style="padding:.4rem;text-align:center;color:#e74c3c;font-weight:600;">{d.get('critical_alerts',0)}</td>
              <td style="padding:.4rem;text-align:center;color:#f39c12;font-weight:600;">{d.get('warning_alerts',0)}</td>
              <td style="padding:.4rem;text-align:center;">{d.get('readings_count',0)}</td>
              <td style="padding:.4rem;text-align:center;">{d.get('avg_value') or '—'}</td>
            </tr>"""

        generated = report_data.get("generated_at", "")[:19].replace("T", " ")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Rapport IoT] {days} jour(s) — {generated[:10]}"
        msg["From"]    = cfg["from_addr"] or cfg["username"]
        msg["To"]      = cfg["to_addr"]

        html = f"""<html><body style="font-family:sans-serif;color:#333;">
        <div style="max-width:640px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
          <div style="background:#1a5c9c;color:#fff;padding:1rem 1.5rem;">
            <h2 style="margin:0;">📄 Rapport IoT — {days} jour(s)</h2>
            <p style="margin:.3rem 0 0;font-size:.85rem;opacity:.8;">Généré le {generated} UTC</p>
          </div>
          <div style="padding:1.2rem 1.5rem;">
            <p style="margin-top:0;">
              <b>Total alertes :</b> {report_data.get('total_alerts',0)} &nbsp;·&nbsp;
              <b>Total lectures :</b> {report_data.get('total_readings',0)}
            </p>
            <table style="width:100%;border-collapse:collapse;font-size:.9rem;">
              <thead>
                <tr style="background:#1a5c9c;color:#fff;">
                  <th style="padding:.5rem .8rem;text-align:left;">Capteur</th>
                  <th style="padding:.5rem;">Total</th>
                  <th style="padding:.5rem;">Crit.</th>
                  <th style="padding:.5rem;">Warn.</th>
                  <th style="padding:.5rem;">Lectures</th>
                  <th style="padding:.5rem;">Moy.</th>
                </tr>
              </thead>
              <tbody style="border:1px solid #ddd;">{rows_html}</tbody>
            </table>
          </div>
          <div style="background:#f5f5f5;padding:.8rem 1.5rem;font-size:.8rem;color:#888;">
            Système d'alertes IoT — INNOV/CCNB 2026
          </div>
        </div></body></html>"""

        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=10) as server:
            server.ehlo()
            server.starttls()
            if cfg.get("username") and cfg.get("password"):
                server.login(cfg["username"], cfg["password"])
            server.sendmail(msg["From"], cfg["to_addr"], msg.as_string())
    except Exception:
        pass


def send_report(report_data: dict, days: int) -> bool:
    """Envoie le rapport par email. Retourne True si envoi lancé."""
    cfg = _load()
    if not cfg.get("active") or not cfg.get("to_addr"):
        return False
    threading.Thread(target=_send_report, args=(report_data, days, cfg), daemon=True).start()
    return True
