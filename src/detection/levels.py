"""
Niveaux d'alerte et résultat d'une analyse.
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class AlertLevel(str, Enum):
    NORMAL   = "NORMAL"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class DetectionResult:
    """Résultat complet de l'analyse d'une lecture capteur."""
    sensor:        str
    value:         float
    unit:          str
    level:         AlertLevel
    method:        str          # "rules" | "zscore" | "iqr"
    reason:        str          # Message lisible par un humain
    timestamp:     datetime     = field(default_factory=lambda: datetime.now(timezone.utc))
    z_score:       float | None = None
    expected_min:  float | None = None
    expected_max:  float | None = None

    def to_dict(self) -> dict:
        return {
            "sensor":       self.sensor,
            "value":        self.value,
            "unit":         self.unit,
            "level":        self.level.value,
            "method":       self.method,
            "reason":       self.reason,
            "timestamp":    self.timestamp.isoformat(),
            "z_score":      self.z_score,
            "expected_min": self.expected_min,
            "expected_max": self.expected_max,
        }

    def is_anomaly(self) -> bool:
        return self.level != AlertLevel.NORMAL

    def __repr__(self):
        return f"<DetectionResult {self.sensor}={self.value} [{self.level.value}] — {self.reason}>"
