"""
Seuils normaux et critiques pour chaque capteur IoT.
Source : normes environnementales standard (eau potable / industrielle).

Le fichier sensors_config.json à la racine du projet permet de surcharger
ces valeurs à chaud (hot-reload via get_sensor_config()).
"""

import json
from pathlib import Path

_SENSORS_FILE = Path(__file__).parent.parent.parent / "sensors_config.json"


def get_sensor_config() -> dict:
    """Retourne la configuration des capteurs (hot-reload depuis sensors_config.json)."""
    if _SENSORS_FILE.exists():
        try:
            return json.loads(_SENSORS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(SENSOR_CONFIG)


SENSOR_CONFIG = {
    "temperature": {
        "unit": "°C",
        "normal":   {"min": 10.0,  "max": 30.0},
        "warning":  {"min": 5.0,   "max": 35.0},
        "critical": {"min": 0.0,   "max": 45.0},
        "baseline": 20.0,
        "noise_std": 1.5,
    },
    "turbidity": {
        "unit": "NTU",
        "normal":   {"min": 0.0,  "max": 4.0},
        "warning":  {"min": 0.0,  "max": 10.0},
        "critical": {"min": 0.0,  "max": 25.0},
        "baseline": 1.5,
        "noise_std": 0.3,
    },
    "ph": {
        "unit": "pH",
        "normal":   {"min": 6.5,  "max": 8.5},
        "warning":  {"min": 5.5,  "max": 9.5},
        "critical": {"min": 4.0,  "max": 11.0},
        "baseline": 7.2,
        "noise_std": 0.2,
    },
}

# Types de scénarios d'anomalies disponibles
ANOMALY_SCENARIOS = [
    "spike_high",    # Pic soudain vers le haut
    "spike_low",     # Pic soudain vers le bas
    "drift_up",      # Dérive progressive vers le haut
    "drift_down",    # Dérive progressive vers le bas
    "noise_burst",   # Bruit intense soudain
    "normal",        # Aucune anomalie
]
