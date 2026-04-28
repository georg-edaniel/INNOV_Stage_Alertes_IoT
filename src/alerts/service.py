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
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
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
        if date_from:
            q = q.filter(Alert.created_at >= date_from)
        if date_to:
            q = q.filter(Alert.created_at <= date_to)
        if search:
            q = q.filter(Alert.reason.ilike(f"%{search}%"))
        return q.order_by(desc(Alert.created_at)).offset(offset).limit(limit).all()

    def count_all(
        self,
        sensor: str | None = None,
        level: str | None = None,
        resolved: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
    ) -> int:
        """Compte les alertes avec les mêmes filtres que get_all."""
        q = self.db.query(Alert)
        if sensor:
            q = q.filter(Alert.sensor == sensor)
        if level:
            q = q.filter(Alert.level == level.upper())
        if resolved is not None:
            q = q.filter(Alert.resolved == resolved)
        if date_from:
            q = q.filter(Alert.created_at >= date_from)
        if date_to:
            q = q.filter(Alert.created_at <= date_to)
        if search:
            q = q.filter(Alert.reason.ilike(f"%{search}%"))
        return q.count()

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
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SensorLog]:
        """Retourne l'historique des lectures capteurs."""
        q = self.db.query(SensorLog)
        if sensor:
            q = q.filter(SensorLog.sensor == sensor)
        if date_from:
            q = q.filter(SensorLog.created_at >= date_from)
        if date_to:
            q = q.filter(SensorLog.created_at <= date_to)
        return q.order_by(desc(SensorLog.created_at)).offset(offset).limit(limit).all()

    def count_logs(
        self,
        sensor: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        q = self.db.query(SensorLog)
        if sensor:
            q = q.filter(SensorLog.sensor == sensor)
        if date_from:
            q = q.filter(SensorLog.created_at >= date_from)
        if date_to:
            q = q.filter(SensorLog.created_at <= date_to)
        return q.count()

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

    def add_note(self, alert_id: int, note: str) -> Alert | None:
        """Ajoute ou remplace la note opérateur d'une alerte."""
        alert = self.get_by_id(alert_id)
        if alert:
            alert.notes = note.strip()
            self.db.commit()
            self.db.refresh(alert)
        return alert

    def set_tags(self, alert_id: int, tags: list[str]) -> Alert | None:
        """Définit les tags d'une alerte (liste de chaînes)."""
        alert = self.get_by_id(alert_id)
        if alert:
            # Nettoie, déduplique, trie
            clean = sorted({t.strip().lower() for t in tags if t.strip()})
            alert.tags = ",".join(clean)
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
        # Notification webhook si CRITICAL
        try:
            from .notifier import notify
            notify(alert.to_dict())
        except Exception:
            pass
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

    def get_mttr(self) -> dict:
        """Mean Time To Resolve par capteur (en secondes). None si aucune alerte résolue."""
        result = {}
        for sensor in ["temperature", "turbidity", "ph"]:
            resolved = self.db.query(Alert).filter(
                Alert.sensor == sensor,
                Alert.resolved == True,       # noqa
                Alert.resolved_at != None,    # noqa
            ).all()
            if not resolved:
                result[sensor] = None
            else:
                durations = [
                    (a.resolved_at - a.created_at).total_seconds()
                    for a in resolved
                    if a.resolved_at and a.created_at
                ]
                result[sensor] = round(sum(durations) / len(durations), 1) if durations else None
        return result

    def get_sensor_health(self) -> dict:
        """Dernier état connu pour chaque capteur (niveau + valeur + horodatage)."""
        health = {}
        for sensor in ["temperature", "turbidity", "ph"]:
            log = self.db.query(SensorLog).filter(
                SensorLog.sensor == sensor
            ).order_by(desc(SensorLog.created_at)).first()
            if log:
                health[sensor] = {
                    "level":     log.level,
                    "value":     round(log.value, 2),
                    "unit":      log.unit,
                    "last_seen": log.created_at.isoformat(),
                }
            else:
                health[sensor] = {"level": "UNKNOWN", "value": None, "unit": "", "last_seen": None}
        return health

    def get_last_alert_time(self) -> str | None:
        """ISO timestamp de la dernière alerte créée."""
        alert = self.db.query(Alert).order_by(desc(Alert.created_at)).first()
        return alert.created_at.isoformat() if alert else None

    def get_report_data(self, days: int = 1) -> dict:
        """Données de rapport agrégées sur les N derniers jours."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        all_alerts = self.db.query(Alert).filter(Alert.created_at >= cutoff).all()
        all_logs   = self.db.query(SensorLog).filter(SensorLog.created_at >= cutoff).all()

        by_sensor = {}
        for sensor in ["temperature", "turbidity", "ph"]:
            s_alerts = [a for a in all_alerts if a.sensor == sensor]
            s_logs   = [l for l in all_logs   if l.sensor == sensor]
            resolved = [a for a in s_alerts if a.resolved and a.resolved_at]

            if resolved:
                durations = [(a.resolved_at - a.created_at).total_seconds() for a in resolved]
                mttr = round(sum(durations) / len(durations), 1)
            else:
                mttr = None

            values = [l.value for l in s_logs]
            by_sensor[sensor] = {
                "total_alerts":    len(s_alerts),
                "critical_alerts": sum(1 for a in s_alerts if a.level == "CRITICAL"),
                "warning_alerts":  sum(1 for a in s_alerts if a.level == "WARNING"),
                "resolved_alerts": len(resolved),
                "readings_count":  len(s_logs),
                "avg_value":       round(sum(values) / len(values), 2) if values else None,
                "min_value":       round(min(values), 2) if values else None,
                "max_value":       round(max(values), 2) if values else None,
                "mttr_seconds":    mttr,
            }

        return {
            "period_days":    days,
            "generated_at":   datetime.now(timezone.utc).isoformat(),
            "total_alerts":   len(all_alerts),
            "total_readings": len(all_logs),
            "by_sensor":      by_sensor,
            "stats":          self.get_stats(),
        }

    def get_heatmap(self, days: int = 7) -> dict:
        """
        Retourne le nombre d'anomalies (WARNING+CRITICAL) par heure (0-23)
        et par jour de semaine (0=lundi … 6=dimanche) sur les N derniers jours.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        logs = self.db.query(SensorLog).filter(
            SensorLog.created_at >= cutoff,
            SensorLog.level.in_(["WARNING", "CRITICAL"]),
        ).all()

        # Grille 7 jours × 24 heures initialisée à 0
        grid = [[0] * 24 for _ in range(7)]
        for log in logs:
            dt = log.created_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            grid[dt.weekday()][dt.hour] += 1

        return {
            "days": days,
            "grid": grid,  # grid[weekday][hour]
            "total": sum(sum(row) for row in grid),
        }

    def get_correlation(self, days: int = 1) -> dict:
        """
        Retourne des paires de valeurs (température, turbidité, pH) horodatées
        pour afficher des graphiques de corrélation.
        Cherche les logs dans une fenêtre de ±30 secondes.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        logs = self.db.query(SensorLog).filter(
            SensorLog.created_at >= cutoff
        ).order_by(SensorLog.created_at).all()

        # Grouper par bucket de 5 secondes
        buckets: dict[int, dict] = {}
        for log in logs:
            dt = log.created_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            bucket = int(dt.timestamp() // 5)
            if bucket not in buckets:
                buckets[bucket] = {}
            buckets[bucket][log.sensor] = log.value

        # Garder seulement les buckets avec les 3 capteurs
        pairs = []
        for b in sorted(buckets):
            d = buckets[b]
            if "temperature" in d and "turbidity" in d and "ph" in d:
                pairs.append({
                    "temperature": round(d["temperature"], 2),
                    "turbidity":   round(d["turbidity"], 2),
                    "ph":          round(d["ph"], 2),
                })

        return {"days": days, "points": pairs, "count": len(pairs)}

    def get_open_duration(self, days: int = 7) -> dict:
        """Durée moyenne (en secondes) des alertes non résolues par niveau."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        now    = datetime.now(timezone.utc)
        open_alerts = self.db.query(Alert).filter(
            Alert.created_at >= cutoff,
            Alert.resolved   == False,  # noqa
        ).all()

        result = {"CRITICAL": None, "WARNING": None}
        for level in ("CRITICAL", "WARNING"):
            subset = [a for a in open_alerts if a.level == level]
            if subset:
                durations = [(now - a.created_at).total_seconds() for a in subset]
                result[level] = round(sum(durations) / len(durations), 1)
        return result

    def _auto_resolve(self, sensor: str):
        """Résout automatiquement les alertes ouvertes quand le capteur revient à la normale."""
        now = datetime.now(timezone.utc)
        self.db.query(Alert).filter(
            Alert.sensor   == sensor,
            Alert.resolved == False,  # noqa
        ).update({"resolved": True, "resolved_at": now})
        self.db.commit()
