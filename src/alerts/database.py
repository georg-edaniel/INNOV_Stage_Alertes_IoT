"""
database.py
-----------
Configuration SQLAlchemy + création de la base de données.
SQLite en dev, PostgreSQL en prod (via DATABASE_URL dans .env).
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./alerts.db")

# SQLite : désactiver check_same_thread pour FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = SessionLocal = None

engine = create_engine(DATABASE_URL, connect_args=connect_args)
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
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # colonne déjà présente
