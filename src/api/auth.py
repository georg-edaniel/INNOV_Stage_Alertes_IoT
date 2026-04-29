"""
auth.py
-------
Authentification simple par cookie de session.
Credentials stockés dans auth_config.json (mot de passe hashé SHA-256).
"""

import json
import hashlib
import secrets
from pathlib import Path
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

CONFIG_FILE = Path(__file__).parent.parent.parent / "auth_config.json"
TEMPLATES_DIR = Path(__file__).parent.parent / "dashboard" / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
auth_router = APIRouter()

_DEFAULT_CONFIG = {
    "enabled": False,
    "username": "admin",
    # SHA-256 de "admin" par défaut
    "password_hash": hashlib.sha256(b"admin").hexdigest(),
    "session_secret": secrets.token_hex(32),
}

# Sessions actives en mémoire { token: username }
_sessions: dict[str, str] = {}


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return {**_DEFAULT_CONFIG, **cfg}
        except Exception:
            pass
    return dict(_DEFAULT_CONFIG)


def is_auth_enabled() -> bool:
    return _load_config().get("enabled", False)


def get_current_user(request: Request) -> str | None:
    """Retourne le nom d'utilisateur si la session est valide, None sinon."""
    if not is_auth_enabled():
        return "guest"
    token = request.cookies.get("session_token")
    return _sessions.get(token)


def require_auth(request: Request) -> str | None:
    """Retourne l'utilisateur connecté ou None (appelant doit rediriger)."""
    return get_current_user(request)


@auth_router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@auth_router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    cfg = _load_config()
    pw_hash = hashlib.sha256(password.encode()).hexdigest()

    if username == cfg["username"] and pw_hash == cfg["password_hash"]:
        token = secrets.token_hex(32)
        _sessions[token] = username
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            "session_token", token,
            httponly=True, samesite="lax", max_age=86400 * 7,
        )
        return response

    return templates.TemplateResponse(request, "login.html", {
        "error": "Identifiants incorrects."
    }, status_code=401)


@auth_router.get("/logout")
def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        _sessions.pop(token, None)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    return response


def get_auth_config() -> dict:
    cfg = _load_config()
    return {"enabled": cfg["enabled"], "username": cfg["username"]}


def update_auth_config(enabled: bool, username: str, password: str | None = None):
    cfg = _load_config()
    cfg["enabled"] = enabled
    cfg["username"] = username
    if password:
        cfg["password_hash"] = hashlib.sha256(password.encode()).hexdigest()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_auth_config()
