"""
models.py
---------
Modèles SQLAlchemy pour les alertes et l'historique des lectures.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from .database import Base


class Alert(Base):
    """
    Une alerte générée par le moteur de détection.

    Champs clés :
    - sensor      : nom du capteur (temperature, turbidity, ph)
    - value       : valeur mesurée
    - level       : NORMAL | WARNING | CRITICAL
    - method      : rules | zscore | iqr
    - reason      : message explicatif
    - acknowledged: True si un opérateur a pris en compte l'alerte
    - resolved    : True si la situation est revenue à la normale
    """
    __tablename__ = "alerts"

    id           = Column(Integer, primary_key=True, index=True)
    sensor       = Column(String(50), nullable=False, index=True)
    value        = Column(Float, nullable=False)
    unit         = Column(String(20), nullable=False)
    level        = Column(String(20), nullable=False, index=True)
    method       = Column(String(20), nullable=False)
    reason       = Column(Text, nullable=False)
    z_score      = Column(Float, nullable=True)
    acknowledged = Column(Boolean, default=False, nullable=False)
    resolved     = Column(Boolean, default=False, nullable=False)
    notes        = Column(Text, nullable=True)          # note opérateur (champ unique)
    tags         = Column(String(200), nullable=True)   # labels CSV (matériel,réseau,…)
    ack_reason    = Column(Text, nullable=True)          # raison de l'acquittement
    snoozed_until = Column(DateTime(timezone=True), nullable=True)  # snooze jusqu'à
    escalated_at  = Column(DateTime(timezone=True), nullable=True)  # date d'escalade WARNING→CRITICAL
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at   = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "sensor":        self.sensor,
            "value":         self.value,
            "unit":          self.unit,
            "level":         self.level,
            "method":        self.method,
            "reason":        self.reason,
            "z_score":       self.z_score,
            "acknowledged":  self.acknowledged,
            "resolved":      self.resolved,
            "notes":         self.notes or "",
            "tags":          self.tags or "",
            "ack_reason":    self.ack_reason or "",
            "snoozed_until": self.snoozed_until.isoformat() if self.snoozed_until else None,
            "escalated_at":  self.escalated_at.isoformat() if self.escalated_at else None,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
            "resolved_at":   self.resolved_at.isoformat() if self.resolved_at else None,
        }

    def __repr__(self):
        return f"<Alert #{self.id} {self.sensor} [{self.level}] {self.created_at}>"


class AuditLog(Base):
    """Journal d'audit des actions opérateur sur les alertes."""
    __tablename__ = "audit_logs"

    id         = Column(Integer, primary_key=True, index=True)
    action     = Column(String(50), nullable=False, index=True)   # acknowledge|resolve|delete|note|tag|archive
    alert_id   = Column(Integer, nullable=True, index=True)       # peut être None si alerte supprimée
    details    = Column(Text, nullable=True)
    user       = Column(String(100), nullable=True, default="système")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "action":     self.action,
            "alert_id":   self.alert_id,
            "details":    self.details or "",
            "user":       self.user or "système",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ArchivedAlert(Base):
    """Alertes résolues archivées (copie depuis alerts après N jours)."""
    __tablename__ = "archived_alerts"

    id           = Column(Integer, primary_key=True)
    original_id  = Column(Integer, nullable=False, index=True)
    sensor       = Column(String(50), nullable=False)
    value        = Column(Float, nullable=False)
    unit         = Column(String(20), nullable=False)
    level        = Column(String(20), nullable=False)
    method       = Column(String(20), nullable=False)
    reason       = Column(Text, nullable=False)
    z_score      = Column(Float, nullable=True)
    acknowledged = Column(Boolean, default=False)
    notes        = Column(Text, nullable=True)
    tags         = Column(String(200), nullable=True)
    created_at   = Column(DateTime(timezone=True), nullable=False)
    resolved_at  = Column(DateTime(timezone=True), nullable=True)
    archived_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "original_id":  self.original_id,
            "sensor":       self.sensor,
            "value":        self.value,
            "unit":         self.unit,
            "level":        self.level,
            "method":       self.method,
            "reason":       self.reason,
            "z_score":      self.z_score,
            "acknowledged": self.acknowledged,
            "notes":        self.notes or "",
            "tags":         self.tags or "",
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "resolved_at":  self.resolved_at.isoformat() if self.resolved_at else None,
            "archived_at":  self.archived_at.isoformat() if self.archived_at else None,
        }


class AlertComment(Base):
    """Fil de commentaires multiples par alerte."""
    __tablename__ = "alert_comments"

    id         = Column(Integer, primary_key=True, index=True)
    alert_id   = Column(Integer, nullable=False, index=True)
    user       = Column(String(100), nullable=False, default="système")
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "alert_id":   self.alert_id,
            "user":       self.user,
            "content":    self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MaintenanceWindow(Base):
    """Fenêtre de maintenance — suppression des alertes pendant la période planifiée."""
    __tablename__ = "maintenance_windows"

    id         = Column(Integer, primary_key=True, index=True)
    sensor     = Column(String(50), nullable=True)   # None = tous les capteurs
    start_dt   = Column(DateTime(timezone=True), nullable=False)
    end_dt     = Column(DateTime(timezone=True), nullable=False)
    reason     = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "sensor":     self.sensor or "all",
            "start_dt":   self.start_dt.isoformat() if self.start_dt else None,
            "end_dt":     self.end_dt.isoformat() if self.end_dt else None,
            "reason":     self.reason or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DeviceKey(Base):
    """Clé API par appareil pour l'endpoint /api/ingest."""
    __tablename__ = "device_keys"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    key_hash    = Column(String(64), nullable=False, unique=True)
    device_id   = Column(String(100), nullable=True)
    active      = Column(Boolean, default=True, nullable=False)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at  = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "device_id":   self.device_id or "",
            "active":      self.active,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
            "expires_at":  self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }


class UserSession(Base):
    """Sessions utilisateur persistées en DB (multi-worker)."""
    __tablename__ = "user_sessions"

    token      = Column(String(64), primary_key=True)
    user       = Column(String(100), nullable=False)
    role       = Column(String(20), nullable=False, default="viewer")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    def to_dict(self) -> dict:
        return {
            "token":      self.token,
            "user":       self.user,
            "role":       self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class PredictionRecord(Base):
    """Historique des prédictions ARIMA/linéaires."""
    __tablename__ = "prediction_records"

    id              = Column(Integer, primary_key=True, index=True)
    sensor          = Column(String(50), nullable=False, index=True)
    method          = Column(String(20), nullable=False)        # arima | linear
    horizon         = Column(Integer, nullable=False, default=20)
    values_json     = Column(Text, nullable=False)              # JSON list
    conf_low_json   = Column(Text, nullable=True)               # JSON list
    conf_high_json  = Column(Text, nullable=True)               # JSON list
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        import json as _json
        return {
            "id":         self.id,
            "sensor":     self.sensor,
            "method":     self.method,
            "horizon":    self.horizon,
            "values":     _json.loads(self.values_json) if self.values_json else [],
            "conf_low":   _json.loads(self.conf_low_json) if self.conf_low_json else [],
            "conf_high":  _json.loads(self.conf_high_json) if self.conf_high_json else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SensorLog(Base):
    """
    Historique de toutes les lectures capteurs (même normales).
    Utile pour les graphiques du dashboard.
    """
    __tablename__ = "sensor_logs"

    id         = Column(Integer, primary_key=True, index=True)
    sensor     = Column(String(50), nullable=False, index=True)
    value      = Column(Float, nullable=False)
    unit       = Column(String(20), nullable=False)
    scenario   = Column(String(50), nullable=True)   # scénario simulateur
    level      = Column(String(20), nullable=False)  # niveau détecté
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "sensor":     self.sensor,
            "value":      self.value,
            "unit":       self.unit,
            "scenario":   self.scenario,
            "level":      self.level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
