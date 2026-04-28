"""
models.py
---------
Modèles SQLAlchemy pour les alertes et l'historique des lectures.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
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
    notes        = Column(Text, nullable=True)          # commentaires opérateur
    tags         = Column(String(200), nullable=True)   # labels CSV (matériel,réseau,…)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at  = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "sensor":       self.sensor,
            "value":        self.value,
            "unit":         self.unit,
            "level":        self.level,
            "method":       self.method,
            "reason":       self.reason,
            "z_score":      self.z_score,
            "acknowledged": self.acknowledged,
            "resolved":     self.resolved,
            "notes":        self.notes or "",
            "tags":         self.tags or "",
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "resolved_at":  self.resolved_at.isoformat() if self.resolved_at else None,
        }

    def __repr__(self):
        return f"<Alert #{self.id} {self.sensor} [{self.level}] {self.created_at}>"


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
