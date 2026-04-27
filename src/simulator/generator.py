"""
generator.py
------------
Génère des lectures de capteurs IoT simulées (température, turbidité, pH)
avec comportements normaux et scénarios d'anomalies réalistes.
"""

import random
import numpy as np
from datetime import datetime, timezone
from typing import Optional
from .config import SENSOR_CONFIG, ANOMALY_SCENARIOS


class SensorReading:
    """Représente une lecture d'un capteur à un instant donné."""

    def __init__(self, sensor: str, value: float, scenario: str, timestamp: Optional[datetime] = None):
        self.sensor    = sensor
        self.value     = round(value, 3)
        self.scenario  = scenario
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.unit      = SENSOR_CONFIG[sensor]["unit"]

    def to_dict(self) -> dict:
        return {
            "sensor":    self.sensor,
            "value":     self.value,
            "unit":      self.unit,
            "scenario":  self.scenario,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self):
        return f"<SensorReading {self.sensor}={self.value}{self.unit} [{self.scenario}]>"


class IoTSimulator:
    """
    Simule un flux de données IoT pour 3 capteurs :
    température, turbidité, pH.

    Chaque appel à `read_all()` retourne les 3 valeurs du moment,
    avec injection aléatoire de scénarios d'anomalies.
    """

    def __init__(self, anomaly_probability: float = 0.15, seed: Optional[int] = None):
        """
        Args:
            anomaly_probability: Probabilité d'injecter une anomalie à chaque lecture (0–1).
            seed: Graine aléatoire pour reproductibilité (tests).
        """
        self.anomaly_probability = anomaly_probability
        self._rng = np.random.default_rng(seed)
        self._random = random.Random(seed)

        # État interne pour les dérives progressives
        self._drift: dict[str, float] = {s: 0.0 for s in SENSOR_CONFIG}
        self._drift_step: dict[str, float] = {s: 0.0 for s in SENSOR_CONFIG}

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def read_all(self) -> list[SensorReading]:
        """Retourne une lecture simulée pour chaque capteur."""
        return [self._read_sensor(sensor) for sensor in SENSOR_CONFIG]

    def read_sensor(self, sensor: str) -> SensorReading:
        """Retourne une lecture pour un capteur spécifique."""
        if sensor not in SENSOR_CONFIG:
            raise ValueError(f"Capteur inconnu : {sensor}. Disponibles : {list(SENSOR_CONFIG)}")
        return self._read_sensor(sensor)

    def reset(self):
        """Remet à zéro les dérives en cours."""
        self._drift      = {s: 0.0 for s in SENSOR_CONFIG}
        self._drift_step = {s: 0.0 for s in SENSOR_CONFIG}

    # ------------------------------------------------------------------
    # Génération interne
    # ------------------------------------------------------------------

    def _read_sensor(self, sensor: str) -> SensorReading:
        cfg      = SENSOR_CONFIG[sensor]
        baseline = cfg["baseline"]
        noise    = float(self._rng.normal(0, cfg["noise_std"]))

        scenario = self._pick_scenario()

        if scenario == "normal":
            value = baseline + noise + self._drift[sensor]

        elif scenario == "spike_high":
            amplitude = (cfg["critical"]["max"] - cfg["normal"]["max"]) * self._rng.uniform(0.5, 1.2)
            value = cfg["normal"]["max"] + amplitude + noise

        elif scenario == "spike_low":
            amplitude = (cfg["normal"]["min"] - cfg["critical"]["min"]) * self._rng.uniform(0.5, 1.2)
            value = cfg["normal"]["min"] - amplitude + noise

        elif scenario == "drift_up":
            self._drift_step[sensor] += cfg["noise_std"] * 0.5
            self._drift[sensor]      += self._drift_step[sensor]
            value = baseline + self._drift[sensor] + noise

        elif scenario == "drift_down":
            self._drift_step[sensor] += cfg["noise_std"] * 0.5
            self._drift[sensor]      -= self._drift_step[sensor]
            value = baseline + self._drift[sensor] + noise

        elif scenario == "noise_burst":
            value = baseline + float(self._rng.normal(0, cfg["noise_std"] * 6))

        else:
            value = baseline + noise

        return SensorReading(sensor=sensor, value=float(value), scenario=scenario)

    def _pick_scenario(self) -> str:
        """Choisit aléatoirement un scénario (normal la plupart du temps)."""
        if self._random.random() < self.anomaly_probability:
            return self._random.choice([s for s in ANOMALY_SCENARIOS if s != "normal"])
        return "normal"
