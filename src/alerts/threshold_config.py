"""
threshold_config.py
-------------------
Store dynamique des seuils de détection.
Permet de modifier les seuils via l'API sans redémarrer le serveur.
Persiste dans thresholds_override.json à côté de ce fichier.
"""

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from ..simulator.config import SENSOR_CONFIG

_STORE_PATH   = Path(__file__).parent / "thresholds_override.json"
_HISTORY_PATH = Path(__file__).parent.parent.parent / "thresholds_history.json"
_overrides: dict = {}


def get_all() -> dict:
    """Config complète (base SENSOR_CONFIG + overrides actifs)."""
    merged = {}
    for sensor, base in SENSOR_CONFIG.items():
        merged[sensor] = deepcopy(base)
        ov = _overrides.get(sensor, {})
        for zone in ("normal", "warning", "critical"):
            if zone in ov:
                merged[sensor][zone].update(ov[zone])
    return merged


def get_sensor(sensor: str) -> dict:
    return get_all().get(sensor, SENSOR_CONFIG.get(sensor, {}))


def update_sensor(sensor: str, zone: str, min_val: float | None, max_val: float | None) -> dict:
    """Met à jour un seuil pour un capteur/zone, persiste et enregistre l'historique."""
    # Valeurs avant modification
    old = deepcopy(_overrides.get(sensor, {}).get(zone, {}))
    _overrides.setdefault(sensor, {}).setdefault(zone, {})
    if min_val is not None:
        _overrides[sensor][zone]["min"] = min_val
    if max_val is not None:
        _overrides[sensor][zone]["max"] = max_val
    _save()
    _append_history(sensor, zone, old, _overrides[sensor][zone])
    return get_all()[sensor]


def reset_all() -> None:
    """Remet tous les seuils aux valeurs par défaut."""
    global _overrides
    _append_history("ALL", "ALL", _overrides, {})
    _overrides = {}
    if _STORE_PATH.exists():
        _STORE_PATH.unlink()


def get_history(limit: int = 30) -> list:
    """Retourne les N dernières modifications de seuils."""
    if not _HISTORY_PATH.exists():
        return []
    try:
        history = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        return history[-limit:][::-1]  # plus récent en premier
    except Exception:
        return []


def _append_history(sensor: str, zone: str, old: dict, new: dict):
    history = []
    if _HISTORY_PATH.exists():
        try:
            history = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensor":    sensor,
        "zone":      zone,
        "old":       old,
        "new":       dict(new),
    })
    # Garder les 200 dernières entrées
    _HISTORY_PATH.write_text(
        json.dumps(history[-200:], indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _save() -> None:
    _STORE_PATH.write_text(json.dumps(_overrides, indent=2))


def _load() -> None:
    global _overrides
    if _STORE_PATH.exists():
        try:
            _overrides = json.loads(_STORE_PATH.read_text())
        except Exception:
            _overrides = {}


_load()
