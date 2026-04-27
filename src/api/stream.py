"""
stream.py
---------
Server-Sent Events (SSE) — pousse les données temps réel au navigateur.

Le navigateur se connecte à GET /api/stream et reçoit un flux JSON
à chaque nouveau cycle du simulateur.

Format SSE :
    data: {"type": "tick", "readings": [...], "alerts": [...], "stats": {...}}\n\n
"""

import asyncio
import json
import queue
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..alerts.database import get_db, SessionLocal
from ..alerts.service import AlertService
from ..detection.engine import AnomalyDetectionEngine
from ..simulator.generator import IoTSimulator

logger = logging.getLogger(__name__)

stream_router = APIRouter()

# ── File de messages partagée (simulateur → SSE clients) ───────────────────
_event_queue: queue.Queue = queue.Queue(maxsize=100)

# Instances partagées (mêmes que routers.py)
_simulator = IoTSimulator(anomaly_probability=0.20)
_engine    = AnomalyDetectionEngine(window_size=30)


def push_tick():
    """
    Appelé par le scheduler à chaque cycle.
    Génère les lectures, les analyse, crée les alertes en DB
    et pousse l'événement dans la file SSE.
    """
    db = SessionLocal()
    try:
        readings = _simulator.read_all()
        results  = _engine.analyze_batch(readings)
        svc      = AlertService(db)
        alerts   = svc.process_batch(results, readings)
        stats    = svc.get_stats()

        event = {
            "type":     "tick",
            "readings": [r.to_dict() for r in readings],
            "results":  [r.to_dict() for r in results],
            "alerts":   [a.to_dict() for a in alerts],
            "stats":    stats,
        }
        # Non-bloquant : si la file est pleine on abandonne silencieusement
        try:
            _event_queue.put_nowait(event)
        except queue.Full:
            pass

    except Exception as e:
        logger.error(f"push_tick error: {e}")
    finally:
        db.close()


# ── Endpoint SSE ───────────────────────────────────────────────────────────

@stream_router.get("/stream")
async def sse_stream():
    """
    Flux SSE — le navigateur se connecte et reçoit les données en temps réel.
    Compatible avec tous les navigateurs modernes (EventSource API).
    """
    async def generator():
        # Message de connexion
        yield "data: " + json.dumps({"type": "connected"}) + "\n\n"

        while True:
            try:
                # Polling non-bloquant de la file
                event = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _event_queue.get(timeout=1)
                )
                yield "data: " + json.dumps(event) + "\n\n"
            except queue.Empty:
                # Heartbeat toutes les secondes pour garder la connexion
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
