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
from .models import Alert, SensorLog, AuditLog, ArchivedAlert, AlertComment, MaintenanceWindow

# Délai minimum entre deux alertes identiques (même capteur + même niveau)
DEDUP_WINDOW_SECONDS = 60


class AlertService:
    """
    Gère le cycle de vie complet des alertes.

    Déduplication : si une alerte du même capteur + même niveau
    a été créée il y a moins de DEDUP_WINDOW_SECONDS, on ne crée pas
    de doublon — on retourne l'alerte existante.
    """

    def __init__(self, db: Session, user: str = "système"):
        self.db   = db
        self.user = user

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
        exclude_outliers: bool = False,
    ) -> list[SensorLog]:
        """Retourne l'historique des lectures capteurs."""
        q = self.db.query(SensorLog)
        if sensor:
            q = q.filter(SensorLog.sensor == sensor)
        if date_from:
            q = q.filter(SensorLog.created_at >= date_from)
        if date_to:
            q = q.filter(SensorLog.created_at <= date_to)
        if exclude_outliers:
            q = q.filter(SensorLog.level == "NORMAL")
        return q.order_by(desc(SensorLog.created_at)).offset(offset).limit(limit).all()

    def count_logs(
        self,
        sensor: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        exclude_outliers: bool = False,
    ) -> int:
        q = self.db.query(SensorLog)
        if sensor:
            q = q.filter(SensorLog.sensor == sensor)
        if date_from:
            q = q.filter(SensorLog.created_at >= date_from)
        if date_to:
            q = q.filter(SensorLog.created_at <= date_to)
        if exclude_outliers:
            q = q.filter(SensorLog.level == "NORMAL")
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

    def acknowledge(self, alert_id: int, reason: str = "") -> Alert | None:
        """Marque une alerte comme vue par un opérateur (avec raison optionnelle)."""
        alert = self.get_by_id(alert_id)
        if alert and not alert.acknowledged:
            alert.acknowledged = True
            if reason.strip():
                alert.ack_reason = reason.strip()
            self.db.commit()
            self.db.refresh(alert)
            details = f"Alerte #{alert_id} acquittée"
            if reason.strip():
                details += f" — raison : {reason.strip()}"
            self._audit("acknowledge", alert_id, details)
        return alert

    def resolve(self, alert_id: int) -> Alert | None:
        """Marque une alerte comme résolue."""
        alert = self.get_by_id(alert_id)
        if alert and not alert.resolved:
            alert.resolved     = True
            alert.resolved_at  = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(alert)
            self._audit("resolve", alert_id, f"Alerte #{alert_id} résolue")
        return alert

    def add_note(self, alert_id: int, note: str) -> Alert | None:
        """Ajoute ou remplace la note opérateur d'une alerte."""
        alert = self.get_by_id(alert_id)
        if alert:
            alert.notes = note.strip()
            self.db.commit()
            self.db.refresh(alert)
            self._audit("note", alert_id, f"Note mise à jour sur #{alert_id}")
        return alert

    def set_tags(self, alert_id: int, tags: list[str]) -> Alert | None:
        """Définit les tags d'une alerte (liste de chaînes)."""
        alert = self.get_by_id(alert_id)
        if alert:
            clean = sorted({t.strip().lower() for t in tags if t.strip()})
            alert.tags = ",".join(clean)
            self.db.commit()
            self.db.refresh(alert)
            self._audit("tag", alert_id, f"Tags: {alert.tags}")
        return alert

    def delete(self, alert_id: int) -> bool:
        """Supprime une alerte. Retourne True si supprimée."""
        alert = self.get_by_id(alert_id)
        if alert:
            self._audit("delete", alert_id, f"Alerte #{alert_id} supprimée ({alert.sensor} {alert.level})")
            self.db.delete(alert)
            self.db.commit()
            return True
        return False

    def delete_bulk(self, ids: list[int]) -> int:
        """Supprime plusieurs alertes. Retourne le nombre supprimé."""
        for aid in ids:
            self._audit("delete", aid, f"Suppression groupée #{aid}")
        count = self.db.query(Alert).filter(Alert.id.in_(ids)).delete(synchronize_session=False)
        self.db.commit()
        return count

    def acknowledge_all(self) -> int:
        """Acquitte toutes les alertes ouvertes. Retourne le nombre mis à jour."""
        count = self.db.query(Alert).filter(
            Alert.acknowledged == False,  # noqa
            Alert.resolved     == False,  # noqa
        ).update({"acknowledged": True})
        self.db.commit()
        self._audit("acknowledge_all", None, f"{count} alertes acquittées")
        return count

    # ------------------------------------------------------------------
    # Commentaires multiples
    # ------------------------------------------------------------------

    def add_comment(self, alert_id: int, content: str) -> AlertComment | None:
        """Ajoute un commentaire à une alerte."""
        alert = self.get_by_id(alert_id)
        if not alert:
            return None
        comment = AlertComment(alert_id=alert_id, user=self.user, content=content.strip())
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        self._audit("comment", alert_id, f"Commentaire ajouté par {self.user}")
        return comment

    def get_comments(self, alert_id: int) -> list[AlertComment]:
        """Retourne tous les commentaires d'une alerte."""
        return self.db.query(AlertComment).filter(
            AlertComment.alert_id == alert_id
        ).order_by(AlertComment.created_at).all()

    def delete_comment(self, comment_id: int) -> bool:
        """Supprime un commentaire. Retourne True si supprimé."""
        c = self.db.query(AlertComment).filter(AlertComment.id == comment_id).first()
        if c:
            self.db.delete(c)
            self.db.commit()
            return True
        return False

    # ------------------------------------------------------------------
    # Fenêtres de maintenance
    # ------------------------------------------------------------------

    def get_maintenance_windows(self) -> list[MaintenanceWindow]:
        return self.db.query(MaintenanceWindow).order_by(desc(MaintenanceWindow.start_dt)).all()

    def create_maintenance_window(
        self, sensor: str | None, start_dt: datetime, end_dt: datetime, reason: str = ""
    ) -> MaintenanceWindow:
        mw = MaintenanceWindow(sensor=sensor or None, start_dt=start_dt, end_dt=end_dt, reason=reason)
        self.db.add(mw)
        self.db.commit()
        self.db.refresh(mw)
        label = sensor or "tous capteurs"
        self._audit("maintenance_add", None, f"Maintenance créée : {label} {start_dt.isoformat()[:16]} → {end_dt.isoformat()[:16]}")
        return mw

    def delete_maintenance_window(self, mw_id: int) -> bool:
        mw = self.db.query(MaintenanceWindow).filter(MaintenanceWindow.id == mw_id).first()
        if mw:
            self._audit("maintenance_del", None, f"Fenêtre maintenance #{mw_id} supprimée")
            self.db.delete(mw)
            self.db.commit()
            return True
        return False

    def is_in_maintenance(self, sensor: str) -> bool:
        """Retourne True si le capteur est actuellement en maintenance."""
        now = datetime.now(timezone.utc)
        from sqlalchemy import or_
        count = self.db.query(MaintenanceWindow).filter(
            MaintenanceWindow.start_dt <= now,
            MaintenanceWindow.end_dt >= now,
            or_(MaintenanceWindow.sensor == sensor, MaintenanceWindow.sensor == None),  # noqa
        ).count()
        return count > 0

    # ------------------------------------------------------------------
    # Détection hors-ligne + escalade (appelées par le scheduler)
    # ------------------------------------------------------------------

    @staticmethod
    def check_offline_sensors(db: Session):
        """Crée une alerte CRITICAL si un capteur n'a pas émis depuis >60s."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
        for sensor in ["temperature", "turbidity", "ph"]:
            log = db.query(SensorLog).filter(
                SensorLog.sensor == sensor
            ).order_by(desc(SensorLog.created_at)).first()

            # Normaliser le timezone du log
            last_ts = None
            if log:
                last_ts = log.created_at
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)

            if last_ts is None or last_ts < cutoff:
                # Vérifier si une alerte "hors ligne" non résolue existe déjà
                existing = db.query(Alert).filter(
                    Alert.sensor   == sensor,
                    Alert.level    == "CRITICAL",
                    Alert.resolved == False,  # noqa
                    Alert.method   == "offline",
                ).first()
                if not existing:
                    svc = AlertService(db)
                    if not svc.is_in_maintenance(sensor):
                        alert = Alert(
                            sensor=sensor, value=0.0, unit="",
                            level="CRITICAL", method="offline",
                            reason=f"Capteur {sensor} hors ligne — aucun signal depuis >60s",
                        )
                        db.add(alert)
                        db.commit()
                        db.refresh(alert)
                        try:
                            from .notifier import notify as webhook_notify
                            webhook_notify(alert.to_dict())
                        except Exception:
                            pass
                        try:
                            from .email_notifier import notify as email_notify
                            email_notify(alert.to_dict())
                        except Exception:
                            pass

    @staticmethod
    def check_storm_alert(db: Session, threshold: int = 5, window_minutes: int = 2):
        """
        Crée une alerte CRITICAL 'tempête' si >= threshold alertes
        ont été créées en moins de window_minutes minutes.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        count  = db.query(Alert).filter(
            Alert.created_at >= cutoff,
            Alert.level.in_(["WARNING", "CRITICAL"]),
            Alert.method != "storm",
        ).count()

        if count >= threshold:
            # Éviter de créer une storm alert en doublon
            existing = db.query(Alert).filter(
                Alert.method   == "storm",
                Alert.resolved == False,  # noqa
                Alert.created_at >= cutoff,
            ).first()
            if not existing:
                storm = Alert(
                    sensor="système", value=float(count), unit="alertes",
                    level="CRITICAL", method="storm",
                    reason=f"Tempête d'alertes : {count} anomalies détectées en {window_minutes} minutes",
                )
                db.add(storm)
                db.commit()
                db.refresh(storm)
                try:
                    from .notifier import notify as webhook_notify
                    webhook_notify(storm.to_dict())
                except Exception:
                    pass
                try:
                    from .email_notifier import notify as email_notify
                    email_notify(storm.to_dict())
                except Exception:
                    pass

    @staticmethod
    def check_escalation(db: Session, escalation_minutes: int = 10):
        """Re-notifie si une alerte CRITICAL n'est pas acquittée depuis N minutes."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=escalation_minutes)
        unacked = db.query(Alert).filter(
            Alert.level        == "CRITICAL",
            Alert.acknowledged == False,  # noqa
            Alert.resolved     == False,  # noqa
            Alert.created_at   <= cutoff,
        ).all()
        for alert in unacked:
            try:
                from .notifier import notify as webhook_notify
                webhook_notify({**alert.to_dict(), "escalation": True})
            except Exception:
                pass
            try:
                from .email_notifier import notify as email_notify
                email_notify(alert.to_dict())
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def _audit(self, action: str, alert_id: int | None, details: str = ""):
        """Enregistre une action dans le journal d'audit."""
        try:
            entry = AuditLog(action=action, alert_id=alert_id, details=details, user=self.user)
            self.db.add(entry)
            self.db.commit()
        except Exception:
            pass

    def get_audit_log(
        self,
        alert_id:  int | None      = None,
        action:    str | None      = None,
        date_from: datetime | None = None,
        date_to:   datetime | None = None,
        limit:  int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Retourne le journal d'audit avec filtres optionnels."""
        q = self.db.query(AuditLog)
        if alert_id is not None:
            q = q.filter(AuditLog.alert_id == alert_id)
        if action:
            q = q.filter(AuditLog.action == action)
        if date_from:
            q = q.filter(AuditLog.created_at >= date_from)
        if date_to:
            q = q.filter(AuditLog.created_at <= date_to)
        return q.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit).all()

    def count_audit_log(
        self,
        alert_id:  int | None      = None,
        action:    str | None      = None,
        date_from: datetime | None = None,
        date_to:   datetime | None = None,
    ) -> int:
        q = self.db.query(AuditLog)
        if alert_id is not None:
            q = q.filter(AuditLog.alert_id == alert_id)
        if action:
            q = q.filter(AuditLog.action == action)
        if date_from:
            q = q.filter(AuditLog.created_at >= date_from)
        if date_to:
            q = q.filter(AuditLog.created_at <= date_to)
        return q.count()

    # ------------------------------------------------------------------
    # Archivage
    # ------------------------------------------------------------------

    def archive_old_alerts(self, days: int = 30) -> int:
        """Déplace les alertes résolues de plus de N jours vers archived_alerts. Retourne le nombre archivé."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        old = self.db.query(Alert).filter(
            Alert.resolved    == True,       # noqa
            Alert.resolved_at != None,       # noqa
            Alert.resolved_at <= cutoff,
        ).all()
        count = 0
        for a in old:
            archived = ArchivedAlert(
                original_id  = a.id,
                sensor       = a.sensor,
                value        = a.value,
                unit         = a.unit,
                level        = a.level,
                method       = a.method,
                reason       = a.reason,
                z_score      = a.z_score,
                acknowledged = a.acknowledged,
                notes        = a.notes,
                tags         = a.tags,
                created_at   = a.created_at,
                resolved_at  = a.resolved_at,
            )
            self.db.add(archived)
            self.db.delete(a)
            count += 1
        if count:
            self._audit("archive", None, f"{count} alertes archivées (>{days} jours)")
            self.db.commit()
        return count

    def unarchive(self, archived_id: int) -> Alert | None:
        """Remet une alerte archivée dans la table alerts."""
        a = self.db.query(ArchivedAlert).filter(ArchivedAlert.id == archived_id).first()
        if not a:
            return None
        restored = Alert(
            sensor       = a.sensor,
            value        = a.value,
            unit         = a.unit,
            level        = a.level,
            method       = a.method,
            reason       = a.reason,
            z_score      = a.z_score,
            acknowledged = a.acknowledged,
            resolved     = True,
            notes        = a.notes,
            tags         = a.tags,
            created_at   = a.created_at,
            resolved_at  = a.resolved_at,
        )
        self.db.add(restored)
        self.db.delete(a)
        self.db.flush()
        self._audit("unarchive", restored.id, f"Alerte restaurée depuis les archives (archive #{archived_id})")
        self.db.commit()
        self.db.refresh(restored)
        return restored

    def get_archived(
        self,
        sensor:    str | None      = None,
        level:     str | None      = None,
        date_from: datetime | None = None,
        date_to:   datetime | None = None,
        limit:  int = 50,
        offset: int = 0,
    ) -> list[ArchivedAlert]:
        q = self.db.query(ArchivedAlert)
        if sensor:    q = q.filter(ArchivedAlert.sensor == sensor)
        if level:     q = q.filter(ArchivedAlert.level  == level.upper())
        if date_from: q = q.filter(ArchivedAlert.archived_at >= date_from)
        if date_to:   q = q.filter(ArchivedAlert.archived_at <= date_to)
        return q.order_by(desc(ArchivedAlert.archived_at)).offset(offset).limit(limit).all()

    def count_archived(
        self,
        sensor:    str | None      = None,
        level:     str | None      = None,
        date_from: datetime | None = None,
        date_to:   datetime | None = None,
    ) -> int:
        q = self.db.query(ArchivedAlert)
        if sensor:    q = q.filter(ArchivedAlert.sensor == sensor)
        if level:     q = q.filter(ArchivedAlert.level  == level.upper())
        if date_from: q = q.filter(ArchivedAlert.archived_at >= date_from)
        if date_to:   q = q.filter(ArchivedAlert.archived_at <= date_to)
        return q.count()

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
        # Notifications (webhook + email) si CRITICAL
        try:
            from .notifier import notify as webhook_notify
            webhook_notify(alert.to_dict())
        except Exception:
            pass
        try:
            from .email_notifier import notify as email_notify
            email_notify(alert.to_dict())
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

    def get_trend(self, days: int = 30, sensor: str | None = None) -> dict:
        """Agrégation journalière des lectures par capteur sur N jours."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = self.db.query(SensorLog).filter(SensorLog.created_at >= cutoff)
        if sensor:
            q = q.filter(SensorLog.sensor == sensor)
        logs = q.order_by(SensorLog.created_at).all()

        # Agrégation par (sensor, date)
        from collections import defaultdict
        buckets: dict[tuple, list] = defaultdict(list)
        for log in logs:
            dt = log.created_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            day = dt.strftime("%Y-%m-%d")
            buckets[(log.sensor, day)].append(log.value)

        sensors = [sensor] if sensor else ["temperature", "turbidity", "ph"]
        result = {}
        for s in sensors:
            days_data = []
            for (sen, day), vals in sorted(buckets.items()):
                if sen == s:
                    days_data.append({"date": day, "avg": round(sum(vals)/len(vals), 2), "count": len(vals)})
            result[s] = days_data

        return {"days": days, "sensors": result}

    def get_comparison(self, period: str = "week") -> dict:
        """Comparaison de la période courante vs la période précédente."""
        now = datetime.now(timezone.utc)
        if period == "month":
            n = 30
        else:
            n = 7

        current_start  = now - timedelta(days=n)
        previous_start = now - timedelta(days=n * 2)
        previous_end   = current_start

        def _stats(df, dt):
            alerts = self.db.query(Alert).filter(Alert.created_at >= df, Alert.created_at < dt).all()
            logs   = self.db.query(SensorLog).filter(SensorLog.created_at >= df, SensorLog.created_at < dt).all()
            total  = len(alerts)
            critical = sum(1 for a in alerts if a.level == "CRITICAL")
            warning  = sum(1 for a in alerts if a.level == "WARNING")
            anomaly_rate = round(total / max(len(logs), 1) * 100, 1)
            return {"total": total, "critical": critical, "warning": warning, "anomaly_rate": anomaly_rate, "readings": len(logs)}

        current  = _stats(current_start,  now)
        previous = _stats(previous_start, previous_end)

        def _delta(c, p):
            if p == 0:
                return None
            return round((c - p) / p * 100, 1)

        return {
            "period": period,
            "current":  current,
            "previous": previous,
            "delta": {
                "total":       _delta(current["total"],       previous["total"]),
                "critical":    _delta(current["critical"],    previous["critical"]),
                "warning":     _delta(current["warning"],     previous["warning"]),
                "anomaly_rate":_delta(current["anomaly_rate"],previous["anomaly_rate"]),
            }
        }

    def compute_adaptive_thresholds(self, days: int = 7) -> dict:
        """
        Calcule des seuils adaptatifs basés sur la distribution des lectures des N derniers jours.
        Retourne des suggestions (non appliquées automatiquement).
        WARNING  = moyenne ± 2 écarts-types
        CRITICAL = moyenne ± 3 écarts-types
        """
        import statistics
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = {}
        for sensor in ["temperature", "turbidity", "ph"]:
            logs = self.db.query(SensorLog).filter(
                SensorLog.sensor == sensor,
                SensorLog.created_at >= cutoff,
            ).all()
            if len(logs) < 10:
                result[sensor] = {"error": "Pas assez de données (min. 10 lectures)"}
                continue
            vals  = [l.value for l in logs]
            mean  = statistics.mean(vals)
            stdev = statistics.stdev(vals)
            result[sensor] = {
                "readings": len(vals),
                "mean":     round(mean, 3),
                "stdev":    round(stdev, 3),
                "suggested": {
                    "normal":   {"min": round(mean - stdev,     2), "max": round(mean + stdev,     2)},
                    "warning":  {"min": round(mean - 2 * stdev, 2), "max": round(mean + 2 * stdev, 2)},
                    "critical": {"min": round(mean - 3 * stdev, 2), "max": round(mean + 3 * stdev, 2)},
                },
            }
        return result

    def _auto_resolve(self, sensor: str):
        """Résout automatiquement les alertes ouvertes quand le capteur revient à la normale."""
        now = datetime.now(timezone.utc)
        self.db.query(Alert).filter(
            Alert.sensor   == sensor,
            Alert.resolved == False,  # noqa
        ).update({"resolved": True, "resolved_at": now})
        self.db.commit()
