"""
conftest.py
-----------
Fixtures pytest pour les tests d'intégration API.
Base SQLite en mémoire (StaticPool pour persistence) + override get_db + TestClient.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.alerts.database import Base, get_db
from src.api.main import app

# ── SQLite en mémoire avec StaticPool ──────────────────────────
# StaticPool garantit que toutes les sessions partagent la même connexion
# → la base persiste pendant toute la durée des tests
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Crée les tables avant les tests (une seule fois pour la session)."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client(create_tables):
    """Client HTTP de test avec base en mémoire et auth désactivée."""
    app.dependency_overrides[get_db] = override_get_db

    # Désactiver l'authentification pour tous les tests
    with patch("src.api.auth.is_auth_enabled", return_value=False):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

    app.dependency_overrides.clear()
