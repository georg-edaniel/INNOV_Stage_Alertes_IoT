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
from .routers import (
    alerts_router, logs_router, sensors_router,
    simulator_router, config_router,
)
from .dashboard import dashboard_router
from .stream import stream_router, push_tick

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "static"

_scheduler: SimulatorScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    init_db()

    _scheduler = SimulatorScheduler(
        interval_seconds=5,
        callback=lambda readings: push_tick(),
        anomaly_probability=0.20,
    )
    _scheduler.start()
    logger.info("Simulateur IoT démarré (intervalle : 5s)")

    yield

    if _scheduler:
        _scheduler.stop()
        logger.info("Simulateur IoT arrêté.")


app = FastAPI(
    title="Système d'Alertes IoT",
    description="Alertes intelligentes basées sur des données IoT simulées — INNOV/CCNB 2026",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(dashboard_router,                              tags=["Dashboard"])
app.include_router(stream_router,      prefix="/api",            tags=["Temps réel"])
app.include_router(alerts_router,      prefix="/api/alerts",     tags=["Alertes"])
app.include_router(logs_router,        prefix="/api/logs",       tags=["Historique"])
app.include_router(sensors_router,     prefix="/api/sensors",    tags=["Capteurs"])
app.include_router(simulator_router,   prefix="/api/simulator",  tags=["Simulateur"])
app.include_router(config_router,      prefix="/api/config",     tags=["Configuration"])


@app.get("/health", tags=["Health"])
def health():
    return {
        "status":            "ok",
        "simulator_running": _scheduler.is_running if _scheduler else False,
        "version":           "2.0.0",
    }
