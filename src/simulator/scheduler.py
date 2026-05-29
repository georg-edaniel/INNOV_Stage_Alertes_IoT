"""
scheduler.py
------------
Lance le simulateur IoT en tâche de fond.
Publie les lectures à intervalle régulier via un callback.

Usage:
    from src.simulator.scheduler import SimulatorScheduler

    def on_reading(readings):
        for r in readings:
            print(r)

    scheduler = SimulatorScheduler(interval_seconds=5, callback=on_reading)
    scheduler.start()
    # ... plus tard ...
    scheduler.stop()
"""

import logging
from typing import Callable
from apscheduler.schedulers.background import BackgroundScheduler
from .generator import IoTSimulator, SensorReading

logger = logging.getLogger(__name__)


class SimulatorScheduler:
    """
    Planificateur qui déclenche le simulateur IoT à intervalle régulier.
    Inclut aussi la détection des capteurs hors-ligne et l'escalade automatique.

    Args:
        interval_seconds: Fréquence d'émission des données (défaut : 5s).
        callback: Fonction appelée avec la liste de SensorReading à chaque cycle.
        anomaly_probability: Probabilité d'anomalie injectée par le simulateur.
        db_factory: SessionLocal pour les jobs offline/escalade.
    """

    def __init__(
        self,
        interval_seconds: int = 5,
        callback: Callable[[list[SensorReading]], None] = None,
        anomaly_probability: float = 0.15,
        db_factory=None,
    ):
        self.interval_seconds = interval_seconds
        self.callback         = callback or self._default_callback
        self.simulator        = IoTSimulator(anomaly_probability=anomaly_probability)
        self._scheduler       = BackgroundScheduler()
        self._running         = False
        self._db_factory      = db_factory

    def start(self):
        if self._running:
            logger.warning("Simulateur déjà en cours.")
            return
        self._scheduler.add_job(
            self._tick,
            trigger="interval",
            seconds=self.interval_seconds,
            id="iot_simulator",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=self.interval_seconds,
        )
        if self._db_factory:
            self._scheduler.add_job(
                self._check_offline,
                trigger="interval",
                seconds=60,
                id="offline_check",
                coalesce=True,
                misfire_grace_time=30,
            )
            self._scheduler.add_job(
                self._check_escalation,
                trigger="interval",
                seconds=120,
                id="escalation_check",
                coalesce=True,
                misfire_grace_time=60,
            )
            self._scheduler.add_job(
                self._check_storm,
                trigger="interval",
                seconds=60,
                id="storm_check",
                coalesce=True,
                misfire_grace_time=30,
            )
            self._scheduler.add_job(
                self._send_scheduled_report,
                trigger="interval",
                minutes=60,
                id="scheduled_report",
                coalesce=True,
                misfire_grace_time=300,
            )
            self._scheduler.add_job(
                self._run_backup,
                trigger="interval",
                hours=6,
                id="auto_backup",
                coalesce=True,
                misfire_grace_time=600,
            )
            self._scheduler.add_job(
                self._run_recalibration,
                trigger="interval",
                hours=6,
                id="auto_recalibration",
                coalesce=True,
                misfire_grace_time=600,
            )
        self._scheduler.start()
        self._running = True
        logger.info(f"Simulateur démarré — intervalle : {self.interval_seconds}s")

    def stop(self):
        if not self._running:
            return
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Simulateur arrêté.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _tick(self):
        try:
            readings = self.simulator.read_all()
            self.callback(readings)
        except Exception as e:
            logger.error(f"Erreur simulateur : {e}")

    def _check_offline(self):
        if not self._db_factory:
            return
        db = self._db_factory()
        try:
            from ..alerts.service import AlertService
            AlertService.check_offline_sensors(db)
        except Exception as e:
            logger.error(f"Erreur vérification hors-ligne : {e}")
        finally:
            db.close()

    def _check_escalation(self):
        if not self._db_factory:
            return
        db = self._db_factory()
        try:
            from ..alerts.service import AlertService
            AlertService.check_escalation(db, escalation_minutes=10)
        except Exception as e:
            logger.error(f"Erreur vérification escalade : {e}")
        finally:
            db.close()

    def _check_storm(self):
        if not self._db_factory:
            return
        db = self._db_factory()
        try:
            from ..alerts.service import AlertService
            AlertService.check_storm_alert(db, threshold=5, window_minutes=2)
        except Exception as e:
            logger.error(f"Erreur vérification tempête : {e}")
        finally:
            db.close()

    def _send_scheduled_report(self):
        if not self._db_factory:
            return
        try:
            from ..alerts.report_scheduler import send_scheduled_report
            send_scheduled_report(self._db_factory)
        except Exception as e:
            logger.error(f"Erreur rapport programmé : {e}")

    def _run_backup(self):
        try:
            from ..alerts.backup import run_backup
            path = run_backup()
            if path:
                logger.info(f"Backup automatique : {path}")
        except Exception as e:
            logger.error(f"Erreur backup automatique : {e}")

    def _run_recalibration(self):
        if not self._db_factory:
            return
        db = self._db_factory()
        try:
            from ..alerts.recalibration import recalibrate_thresholds
            changes = recalibrate_thresholds(db)
            if changes:
                logger.info(f"Recalibration auto : {list(changes.keys())}")
        except Exception as e:
            logger.error(f"Erreur recalibration auto : {e}")
        finally:
            db.close()

    @staticmethod
    def _default_callback(readings: list[SensorReading]):
        for r in readings:
            logger.info(r)
