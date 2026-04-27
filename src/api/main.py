"""
main.py
-------
Point d'entrée FastAPI.
Lance le simulateur IoT en arrière-plan et expose les endpoints d'alertes.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..alerts.database import init_db
from ..simulator.scheduler import SimulatorScheduler
from .routers import alerts_router, logs_router, simulator_router
from .dashboard import dashboard_router
from .stream import stream_router, push_tick

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "static"

# Scheduler global (démarré dans le lifespan)
_scheduler: SimulatorScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    # 1. Créer les tables DB
    init_db()

    # 2. Démarrer le simulateur IoT en arrière-plan (toutes les 5 secondes)
    _scheduler = SimulatorScheduler(
        interval_seconds=5,
        callback=lambda readings: push_tick(),   # push_tick gère sa propre session DB
        anomaly_probability=0.20,
    )
    _scheduler.start()
    logger.info("Simulateur IoT démarré (intervalle : 5s)")

    yield

    # 3. Arrêt propre du scheduler
    if _scheduler:
        _scheduler.stop()
        logger.info("Simulateur IoT arrêté.")


app = FastAPI(
    title="Système d'Alertes IoT",
    description="Alertes intelligentes basées sur des données IoT simulées — INNOV/CCNB 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(dashboard_router,                          tags=["Dashboard"])
app.include_router(stream_router,    prefix="/api",           tags=["Temps réel"])
app.include_router(alerts_router,    prefix="/api/alerts",    tags=["Alertes"])
app.include_router(logs_router,      prefix="/api/logs",      tags=["Historique"])
app.include_router(simulator_router, prefix="/api/simulator", tags=["Simulateur"])


@app.get("/health", tags=["Health"])
def health():
    return {
        "status":            "ok",
        "simulator_running": _scheduler.is_running if _scheduler else False,
    }
