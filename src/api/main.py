"""
main.py
-------
Point d'entrée FastAPI.
Lance le simulateur IoT en arrière-plan et expose les endpoints d'alertes.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..alerts.database import init_db
from .routers import alerts_router, logs_router, simulator_router
from .dashboard import dashboard_router

STATIC_DIR    = Path(__file__).parent.parent / "dashboard" / "static"
TEMPLATES_DIR = Path(__file__).parent.parent / "dashboard" / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage : créer les tables
    init_db()
    yield
    # Arrêt : rien de spécial


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
app.include_router(alerts_router,    prefix="/api/alerts",    tags=["Alertes"])
app.include_router(logs_router,      prefix="/api/logs",      tags=["Historique"])
app.include_router(simulator_router, prefix="/api/simulator", tags=["Simulateur"])


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "IoT Alert System", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
