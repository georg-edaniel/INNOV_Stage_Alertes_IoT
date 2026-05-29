"""
recalibration.py
----------------
Recalibration automatique des seuils d'alerte.

Calcule les percentiles P5/P95/P1/P99 sur les 24 dernières heures de logs,
et met à jour les seuils dans thresholds_override.json si l'écart est > 15%.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

THRESHOLDS_FILE = Path(__file__).parent.parent.parent / "thresholds_override.json"


def recalibrate_thresholds(db, window_hours: int = 24) -> dict:
    """
    Recalibre les seuils pour chaque capteur en se basant sur les lectures récentes.

    Parameters
    ----------
    db : Session SQLAlchemy
    window_hours : fenêtre de données (défaut 24h)

    Returns
    -------
    dict : { sensor: { "warning_min": ..., "warning_max": ..., ... } }
    """
    import numpy as np
    from .models import SensorLog

    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    logs  = db.query(SensorLog).filter(SensorLog.created_at >= since).all()

    if not logs:
        logger.info("recalibration: aucune donnée disponible")
        return {}

    # Grouper par capteur
    by_sensor: dict[str, list[float]] = {}
    for log in logs:
        by_sensor.setdefault(log.sensor, []).append(log.value)

    # Charger les seuils actuels
    overrides = {}
    if THRESHOLDS_FILE.exists():
        try:
            overrides = json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8"))
        except Exception:
            overrides = {}

    changes = {}
    for sensor, values in by_sensor.items():
        if len(values) < 20:
            continue  # pas assez de données

        arr = np.array(values)
        p1  = float(np.percentile(arr, 1))
        p5  = float(np.percentile(arr, 5))
        p95 = float(np.percentile(arr, 95))
        p99 = float(np.percentile(arr, 99))

        existing = overrides.get(sensor, {}).get("adaptive", {})

        new_adaptive = {
            "warning_min": round(p5, 3),
            "warning_max": round(p95, 3),
            "critical_min": round(p1, 3),
            "critical_max": round(p99, 3),
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            "samples": len(values),
        }

        # Vérifier si l'écart est > 15% par rapport aux valeurs existantes
        def _changed(new_val: float, old_val: float | None) -> bool:
            if old_val is None or old_val == 0:
                return True
            return abs(new_val - old_val) / abs(old_val) > 0.15

        if any(
            _changed(new_adaptive[k], existing.get(k))
            for k in ("warning_min", "warning_max", "critical_min", "critical_max")
        ):
            if sensor not in overrides:
                overrides[sensor] = {}
            overrides[sensor]["adaptive"] = new_adaptive
            changes[sensor] = new_adaptive
            logger.info(f"Recalibration {sensor}: {new_adaptive}")

    if changes:
        THRESHOLDS_FILE.write_text(
            json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return changes
