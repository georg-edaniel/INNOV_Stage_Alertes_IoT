"""
service.py
----------
Service de gestion des alertes :
  - Création avec déduplication (évite le spam)
  - Historique paginé
  - Acquittement et résolution
  - Statistiques
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from ..detection.levels import AlertLevel, DetectionResult
from ..simulator.generator import SensorReading
from .models import Alert, SensorLog

# Délai minimum entre deux alertes identiques (même capteur + même niveau)
DEDUP_WINDOW_SECONDS = 60


class AlertService:
    """
    Gère le cycle de vie complet des alertes.

    Déduplication : si une alerte du même capteur + même niveau
    a été créée il y a moins de DEDUP_WINDOW_SECONDS, on ne crée pas
    de doublon — on retourne l'alerte existante.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Création
    # ------------------------------------------------------------------

    def process(self, result: DetectionResult, reading: SensorReading | None = None) -> Alert | None:
        """
        Traite un résultat de détection :
        - Enregistre la lecture dans sensor_logs
        - Crée une alerte si NORMAL → non, WARNING/CRITICAL → oui (avec dédup)

        Retourne l'alerte créée, ou None si normale / dupliquée.
        """
        # Toujours logger la lecture
        self._log_reading(result, reading)

        if result.level == AlertLevel.NORMAL:
            # Résoudre les alertes ouvertes sur ce capteur si retour à la normale
            self._auto_resolve(result.sensor)
            return None

        return self._create_or_dedup(result)

    def process_batch(self, results: list[DetectionResult], readings: list[SensorReading] | None = None) -> list[Alert]:
        """Traite un lot de résultats et retourne les alertes créées."""
        alerts = []
        for i, result in enumerate(results):
            reading = readings[i] if readings and i < len(readings) else None
            alert = self.process(result, reading)
            if alert:
                alerts.append(alert)
        return alerts

    # ------------------------------------------------------------------
    # Consultation
    # ------------------------------------------------------------------

    def get_all(
        self,
        sensor: str | None = None,
        level: str | None = None,
        resolved: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Alert]:
        """Retourne les alertes filtrées, les plus récentes en premier."""
        q = self.db.query(Alert)
        if sensor:
            q = q.filter(Alert.sensor == sensor)
        if level:
            q = q.filter(Alert.level == level.upper())
        if resolved is not None:
            q = q.filter(Alert.resolved == resolved)
        return q.order_by(desc(Alert.created_at)).offset(offset).limit(limit).all()

    def get_by_id(self, alert_id: int) -> Alert | None:
        return self.db.query(Alert).filter(Alert.id == alert_id).first()

    def get_open_count(self) -> dict:
        """Compte les alertes ouvertes par niveau."""
        q = self.db.query(Alert).filter(Alert.resolved == False)  # noqa
        return {
            "warning":  q.filter(Alert.level == "WARNING").count(),
            "critical": q.filter(Alert.level == "CRITICAL").count(),
        }

    def get_logs(
        self,
        sensor: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SensorLog]:
        """Retourne l'historique des lectures capteurs."""
        q = self.db.query(SensorLog)
        if sensor:
            q = q.filter(SensorLog.sensor == sensor)
        return q.order_by(desc(SensorLog.created_at)).offset(offset).limit(limit).all()

    def get_stats(self) -> dict:
        """Statistiques globales des alertes."""
        total    = self.db.query(Alert).count()
        open_    = self.db.query(Alert).filter(Alert.resolved == False).count()  # noqa
        critical = self.db.query(Alert).filter(Alert.level == "CRITICAL").count()
        warning  = self.db.query(Alert).filter(Alert.level == "WARNING").count()
        ack      = self.db.query(Alert).filter(Alert.acknowledged == True).count()  # noqa
        return {
            "total":        total,
            "open":         open_,
            "critical":     critical,
            "warning":      warning,
            "acknowledged": ack,
            "resolved":     total - open_,
        }

    # ------------------------------------------------------------------
    # Actions opérateur
    # ------------------------------------------------------------------

    def acknowledge(self, alert_id: int) -> Alert | None:
        """Marque une alerte comme vue par un opérateur."""
        alert = self.get_by_id(alert_id)
        if alert and not alert.acknowledged:
            alert.acknowledged = True
            self.db.commit()
            self.db.refresh(alert)
        return alert

    def resolve(self, alert_id: int) -> Alert | None:
        """Marque une alerte comme résolue."""
        alert = self.get_by_id(alert_id)
        if alert and not alert.resolved:
            alert.resolved     = True
            alert.resolved_at  = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(alert)
        return alert

    def acknowledge_all(self) -> int:
        """Acquitte toutes les alertes ouvertes. Retourne le nombre mis à jour."""
        count = self.db.query(Alert).filter(
            Alert.acknowledged == False,  # noqa
            Alert.resolved     == False,  # noqa
        ).update({"acknowledged": True})
        self.db.commit()
        return count

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _create_or_dedup(self, result: DetectionResult) -> Alert:
        """Crée l'alerte ou retourne le doublon récent."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=DEDUP_WINDOW_SECONDS)
        existing = self.db.query(Alert).filter(
            and_(
                Alert.sensor    == result.sensor,
                Alert.level     == result.level.value,
                Alert.resolved  == False,  # noqa
                Alert.created_at >= cutoff,
            )
        ).first()

        if existing:
            return existing  # doublon — on ne crée pas

        alert = Alert(
            sensor  = result.sensor,
            value   = result.value,
            unit    = result.unit,
            level   = result.level.value,
            method  = result.method,
            reason  = result.reason,
            z_score = result.z_score,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def _log_reading(self, result: DetectionResult, reading: SensorReading | None):
        log = SensorLog(
            sensor   = result.sensor,
            value    = result.value,
            unit     = result.unit,
            scenario = reading.scenario if reading else None,
            level    = result.level.value,
        )
        self.db.add(log)
        self.db.commit()

    def _auto_resolve(self, sensor: str):
        """Résout automatiquement les alertes ouvertes quand le capteur revient à la normale."""
        now = datetime.now(timezone.utc)
        self.db.query(Alert).filter(
            Alert.sensor   == sensor,
            Alert.resolved == False,  # noqa
        ).update({"resolved": True, "resolved_at": now})
        self.db.commit()
