"""
autoencoder.py
--------------
Détecteur d'anomalies par autoencoder linéaire (PCA via SVD).
Approche numpy pur — pas de dépendance Keras/TensorFlow.

Principe :
  1. Fenêtre glissante de N valeurs → vecteur
  2. Décomposition SVD pour encoder/décoder (reconstruction)
  3. Erreur de reconstruction > seuil → anomalie
"""

import numpy as np
from collections import deque
from ..simulator.generator import SensorReading
from .levels import AlertLevel, DetectionResult


class LinearAutoencoderDetector:
    """
    Autoencoder linéaire (PCA) basé sur la décomposition SVD.

    Fenêtre glissante de `window_size` points → matrice Hankel
    → SVD → reconstruction → erreur MSE.

    Se réentraîne tous les `retrain_every` points.
    """

    def __init__(self, window_size: int = 20, n_components: int = 3, retrain_every: int = 50):
        self.window_size   = window_size
        self.n_components  = n_components
        self.retrain_every = retrain_every

        self._buffers:    dict[str, deque] = {}
        self._U:          dict[str, np.ndarray] = {}
        self._mean:       dict[str, np.ndarray] = {}
        self._errors:     dict[str, deque] = {}
        self._tick_count: dict[str, int] = {}

    def _buffer(self, sensor: str) -> deque:
        if sensor not in self._buffers:
            self._buffers[sensor]    = deque(maxlen=self.window_size * 4)
            self._errors[sensor]     = deque(maxlen=100)
            self._tick_count[sensor] = 0
        return self._buffers[sensor]

    def _build_hankel(self, values: list, rows: int) -> np.ndarray:
        """Construit une matrice Hankel (fenêtre glissante) de shape (n_rows, window_size)."""
        n = len(values)
        cols = self.window_size
        m = []
        for i in range(rows):
            if i + cols <= n:
                m.append(values[i:i + cols])
        return np.array(m, dtype=float) if m else np.empty((0, cols))

    def _train(self, sensor: str):
        """Entraîne l'autoencoder PCA sur le buffer courant."""
        buf    = list(self._buffer(sensor))
        if len(buf) < self.window_size + self.n_components:
            return
        n_rows = len(buf) - self.window_size + 1
        H      = self._build_hankel(buf, n_rows)
        if H.shape[0] < self.n_components:
            return
        mean = H.mean(axis=0)
        Hc   = H - mean
        try:
            U, _, _ = np.linalg.svd(Hc, full_matrices=False)
            # On garde les n_components premières composantes
            self._U[sensor]    = U[:, :self.n_components]  # type: ignore
            self._mean[sensor] = mean
        except np.linalg.LinAlgError:
            pass

    def _reconstruct_error(self, sensor: str, window_vec: np.ndarray) -> float | None:
        """Erreur de reconstruction MSE pour un vecteur fenêtre."""
        if sensor not in self._U or sensor not in self._mean:
            return None
        U    = self._U[sensor]
        mean = self._mean[sensor]
        xc   = window_vec - mean
        # Projection dans l'espace réduit et reconstruction
        coords = xc @ U
        xhat   = coords @ U.T
        error  = float(np.mean((xc - xhat) ** 2))
        return error

    def analyze(self, reading: SensorReading) -> DetectionResult:
        from ..simulator.config import SENSOR_CONFIG
        sensor = reading.sensor
        value  = reading.value
        cfg    = SENSOR_CONFIG.get(sensor, {})
        unit   = cfg.get("unit", reading.unit)

        buf = self._buffer(sensor)
        buf.append(value)
        self._tick_count[sensor] = self._tick_count.get(sensor, 0) + 1

        # Réentrainement périodique
        if self._tick_count[sensor] % self.retrain_every == 0:
            self._train(sensor)

        # Besoin d'assez de données
        if len(buf) < self.window_size:
            return DetectionResult(
                sensor=sensor, value=value, unit=unit,
                level=AlertLevel.NORMAL, method="autoencoder",
                reason=f"Autoencoder: calibration ({len(buf)}/{self.window_size})",
                timestamp=reading.timestamp,
            )

        # Entraîner si pas encore fait
        if sensor not in self._U:
            self._train(sensor)
            return DetectionResult(
                sensor=sensor, value=value, unit=unit,
                level=AlertLevel.NORMAL, method="autoencoder",
                reason="Autoencoder: premier entraînement",
                timestamp=reading.timestamp,
            )

        # Erreur de reconstruction
        window_vec = np.array(list(buf)[-self.window_size:], dtype=float)
        error = self._reconstruct_error(sensor, window_vec)
        if error is None:
            return DetectionResult(
                sensor=sensor, value=value, unit=unit,
                level=AlertLevel.NORMAL, method="autoencoder",
                reason="Autoencoder: modèle non prêt",
                timestamp=reading.timestamp,
            )

        errors = self._errors[sensor]
        errors.append(error)

        if len(errors) < 10:
            return DetectionResult(
                sensor=sensor, value=value, unit=unit,
                level=AlertLevel.NORMAL, method="autoencoder",
                reason=f"Autoencoder: collecte des erreurs ({len(errors)}/10)",
                timestamp=reading.timestamp,
            )

        err_mean = float(np.mean(list(errors)))
        err_std  = float(np.std(list(errors)))

        if err_std == 0:
            level  = AlertLevel.NORMAL
            reason = f"Autoencoder: aucune variation (erreur={error:.6f})"
        elif error > err_mean + 3 * err_std:
            level  = AlertLevel.CRITICAL
            reason = (f"Autoencoder CRITIQUE — erreur reconstruction anormale "
                      f"({error:.4f} > μ+3σ={err_mean + 3 * err_std:.4f})")
        elif error > err_mean + 2 * err_std:
            level  = AlertLevel.WARNING
            reason = (f"Autoencoder ALERTE — erreur reconstruction élevée "
                      f"({error:.4f} > μ+2σ={err_mean + 2 * err_std:.4f})")
        else:
            level  = AlertLevel.NORMAL
            reason = f"Autoencoder: reconstruction normale (erreur={error:.4f})"

        return DetectionResult(
            sensor=sensor, value=value, unit=unit,
            level=level, method="autoencoder",
            reason=reason,
            timestamp=reading.timestamp,
        )
