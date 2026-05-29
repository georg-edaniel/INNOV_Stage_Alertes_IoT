"""
database.py
-----------
Configuration SQLAlchemy + création de la base de données.
SQLite en dev, PostgreSQL en prod (via DATABASE_URL dans .env).
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./alerts.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite : désactiver check_same_thread + timeout 30s pour éviter "database is locked"
connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}

engine = SessionLocal = None

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    # SQLite : pool_size non applicable, on utilise StaticPool implicite
)

# Activer WAL mode sur SQLite pour autoriser les lectures concurrentes
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")
        dbapi_conn.execute("PRAGMA busy_timeout=30000")

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dépendance FastAPI : fournit une session DB puis la ferme."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Crée toutes les tables si elles n'existent pas + migrations légères."""
    from . import models  # noqa — import pour enregistrer les modèles
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)
    # Migrations légères SQLite (colonnes ajoutées progressivement)
    migrations = [
        "ALTER TABLE alerts ADD COLUMN notes TEXT",
        "ALTER TABLE alerts ADD COLUMN tags VARCHAR(200)",
        "ALTER TABLE audit_logs ADD COLUMN user VARCHAR(100)",
        "ALTER TABLE alerts ADD COLUMN ack_reason TEXT",
        "ALTER TABLE alerts ADD COLUMN snoozed_until DATETIME",
        "ALTER TABLE alerts ADD COLUMN escalated_at DATETIME",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # colonne déjà présente
