"""Tests du simulateur IoT."""

import pytest
from src.simulator.generator import IoTSimulator, SensorReading
from src.simulator.config import SENSOR_CONFIG


@pytest.fixture
def sim():
    return IoTSimulator(anomaly_probability=0.0, seed=42)  # 0% anomalie pour tests déterministes


def test_read_all_retourne_3_capteurs(sim):
    readings = sim.read_all()
    assert len(readings) == 3
    sensors = {r.sensor for r in readings}
    assert sensors == {"temperature", "turbidity", "ph"}


def test_valeurs_normales_dans_plage(sim):
    for _ in range(50):
        readings = sim.read_all()
        for r in readings:
            cfg = SENSOR_CONFIG[r.sensor]
            assert cfg["critical"]["min"] <= r.value <= cfg["critical"]["max"] * 1.5, (
                f"{r.sensor}={r.value} hors plage critique"
            )


def test_to_dict_contient_champs_requis(sim):
    r = sim.read_sensor("temperature")
    d = r.to_dict()
    assert {"sensor", "value", "unit", "scenario", "timestamp"} <= d.keys()


def test_sensor_inconnu_leve_erreur(sim):
    with pytest.raises(ValueError, match="Capteur inconnu"):
        sim.read_sensor("oxygene")


def test_anomalie_spike_high_depasse_normale():
    sim = IoTSimulator(anomaly_probability=1.0, seed=0)
    # Forcer spike_high sur température
    sim._random.seed(0)
    readings = []
    for _ in range(100):
        r = sim.read_sensor("temperature")
        readings.append(r)
    spikes = [r for r in readings if r.scenario == "spike_high"]
    if spikes:
        cfg = SENSOR_CONFIG["temperature"]
        for r in spikes:
            assert r.value > cfg["normal"]["max"]


def test_reset_efface_derive():
    sim = IoTSimulator(anomaly_probability=0.0, seed=42)
    # Forcer une dérive
    sim._drift["temperature"] = 50.0
    sim.reset()
    assert sim._drift["temperature"] == 0.0


def test_sensor_reading_repr():
    r = SensorReading("ph", 7.5, "normal")
    assert "ph" in repr(r)
    assert "7.5" in repr(r)
