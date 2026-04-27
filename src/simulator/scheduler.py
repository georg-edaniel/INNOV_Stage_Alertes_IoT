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

    Args:
        interval_seconds: Fréquence d'émission des données (défaut : 5s).
        callback: Fonction appelée avec la liste de SensorReading à chaque cycle.
        anomaly_probability: Probabilité d'anomalie injectée par le simulateur.
    """

    def __init__(
        self,
        interval_seconds: int = 5,
        callback: Callable[[list[SensorReading]], None] = None,
        anomaly_probability: float = 0.15,
    ):
        self.interval_seconds = interval_seconds
        self.callback         = callback or self._default_callback
        self.simulator        = IoTSimulator(anomaly_probability=anomaly_probability)
        self._scheduler       = BackgroundScheduler()
        self._running         = False

    def start(self):
        if self._running:
            logger.warning("Simulateur déjà en cours.")
            return
        self._scheduler.add_job(
            self._tick,
            trigger="interval",
            seconds=self.interval_seconds,
            id="iot_simulator",
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

    @staticmethod
    def _default_callback(readings: list[SensorReading]):
        for r in readings:
            logger.info(r)
