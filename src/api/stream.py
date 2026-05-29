"""
stream.py
---------
Temps réel : Server-Sent Events (SSE) + WebSocket.

SSE   : GET  /api/stream    — flux JSON, compatible EventSource
WebSocket : WS /api/ws  — bidirectionnel, préféré si disponible

Format événement :
    {"type": "tick", "readings": [...], "alerts": [...], "stats": {...}}
"""

import asyncio
import json
import queue
import logging
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..alerts.database import SessionLocal
from ..alerts.service import AlertService
from ..detection.engine import AnomalyDetectionEngine
from ..simulator.generator import IoTSimulator

logger = logging.getLogger(__name__)

stream_router = APIRouter()

# ── File de messages partagée (simulateur → SSE/WS clients) ────────────────
_event_queue: queue.Queue = queue.Queue(maxsize=100)

# Instances partagées (mêmes que routers.py)
_simulator = IoTSimulator(anomaly_probability=0.20)
_engine    = AnomalyDetectionEngine(window_size=30)


# ── WebSocket ConnectionManager ─────────────────────────────────────────────

class ConnectionManager:
    """Gère les connexions WebSocket actives."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.debug(f"WS connecté — total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        logger.debug(f"WS déconnecté — total: {len(self._connections)}")

    async def broadcast(self, data: Any):
        """Envoie un message JSON à tous les clients connectés."""
        if not self._connections:
            return
        message = json.dumps(data, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


ws_manager = ConnectionManager()


def set_simulator_probability(prob: float) -> None:
    """Modifie la probabilité d'anomalie du simulateur SSE."""
    _simulator.anomaly_probability = prob


def push_tick():
    """
    Appelé par le scheduler à chaque cycle.
    Génère les lectures, les analyse, crée les alertes en DB
    et pousse l'événement dans la file SSE + WebSocket.
    """
    db = SessionLocal()
    try:
        readings = _simulator.read_all()
        results  = _engine.analyze_batch(readings)
        svc      = AlertService(db)
        alerts   = svc.process_batch(results, readings)
        stats    = svc.get_stats()
        health   = svc.get_sensor_health()

        # Métriques Prometheus
        try:
            from .metrics import record_reading, record_alert, update_active_alerts_from_db
            for r in readings:
                record_reading(r.sensor)
            for a in alerts:
                record_alert(a.sensor, a.level)
            update_active_alerts_from_db(db)
        except Exception:
            pass

        event = {
            "type":          "tick",
            "readings":      [r.to_dict() for r in readings],
            "results":       [r.to_dict() for r in results],
            "alerts":        [a.to_dict() for a in alerts],
            "stats":         stats,
            "sensor_health": health,
        }
        # SSE : non-bloquant
        try:
            _event_queue.put_nowait(event)
        except queue.Full:
            pass

        # WebSocket : broadcaster async dans le loop principal
        if ws_manager.count > 0:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(ws_manager.broadcast(event), loop)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"push_tick error: {e}")
    finally:
        db.close()


# ── Endpoint SSE ────────────────────────────────────────────────────────────

@stream_router.get("/stream")
async def sse_stream():
    """Flux SSE — le navigateur se connecte et reçoit les données en temps réel."""
    async def generator():
        yield "data: " + json.dumps({"type": "connected"}) + "\n\n"
        while True:
            try:
                event = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _event_queue.get(timeout=1)
                )
                yield "data: " + json.dumps(event) + "\n\n"
            except queue.Empty:
                yield ": heartbeat\n\n"
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSE generator error: {e}")
                break

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Endpoint WebSocket ───────────────────────────────────────────────────────

@stream_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket temps réel — préféré au SSE quand disponible."""
    await ws_manager.connect(ws)
    try:
        # Message de bienvenue
        await ws.send_text(json.dumps({"type": "connected", "transport": "websocket"}))
        # Garder la connexion ouverte (attendre déconnexion client)
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Heartbeat
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS error: {e}")
    finally:
        ws_manager.disconnect(ws)
