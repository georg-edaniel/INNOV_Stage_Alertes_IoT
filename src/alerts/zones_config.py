"""
zones_config.py
---------------
Associe chaque capteur à une zone géographique (nom, coordonnées).
Config persistée dans zones_config.json.
"""

import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent.parent / "zones_config.json"

_DEFAULTS: dict[str, dict] = {
    "temperature": {
        "zone":  "Zone A",
        "label": "Capteur Température",
        "lat":   46.8139,
        "lon":   -71.2082,
    },
    "turbidity": {
        "zone":  "Zone B",
        "label": "Capteur Turbidité",
        "lat":   46.8160,
        "lon":   -71.2050,
    },
    "ph": {
        "zone":  "Zone A",
        "label": "Capteur pH",
        "lat":   46.8120,
        "lon":   -71.2100,
    },
}


def load_zones() -> dict:
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # Merge with defaults so new sensors always have a config
            result = {}
            for sensor, defaults in _DEFAULTS.items():
                result[sensor] = {**defaults, **saved.get(sensor, {})}
            return result
        except Exception:
            pass
    return {s: dict(d) for s, d in _DEFAULTS.items()}


def save_zones(zones: dict) -> dict:
    """Enregistre la config complète des zones."""
    CONFIG_FILE.write_text(
        json.dumps(zones, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return load_zones()


def update_sensor_zone(
    sensor: str,
    zone: str | None = None,
    label: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    """Met à jour les infos de zone d'un capteur."""
    zones = load_zones()
    if sensor not in zones:
        zones[sensor] = dict(_DEFAULTS.get(sensor, {"zone": "Zone A", "label": sensor, "lat": 0.0, "lon": 0.0}))
    if zone  is not None: zones[sensor]["zone"]  = zone
    if label is not None: zones[sensor]["label"] = label
    if lat   is not None: zones[sensor]["lat"]   = lat
    if lon   is not None: zones[sensor]["lon"]   = lon
    return save_zones(zones)
