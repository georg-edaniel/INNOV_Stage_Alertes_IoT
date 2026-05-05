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
    # Rôles : admin | operator | viewer
    "users": {},  # { "username": { "password_hash": "...", "role": "admin|operator|viewer" } }
    "default_role": "admin",
}

# Sessions actives en mémoire { token: { "user": str, "role": str } }
_sessions: dict[str, dict] = {}


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
    sess  = _sessions.get(token)
    return sess["user"] if sess else None


def get_current_role(request: Request) -> str:
    """Retourne le rôle de l'utilisateur connecté : admin | operator | viewer | guest."""
    if not is_auth_enabled():
        return "admin"
    token = request.cookies.get("session_token")
    sess  = _sessions.get(token)
    return sess["role"] if sess else "viewer"


def require_auth(request: Request) -> str | None:
    """Retourne l'utilisateur connecté ou None (appelant doit rediriger)."""
    return get_current_user(request)


def can_write(request: Request) -> bool:
    """Vérifie que l'utilisateur a le droit d'écriture (admin ou operator)."""
    return get_current_role(request) in ("admin", "operator")


def is_admin(request: Request) -> bool:
    """Vérifie que l'utilisateur est admin."""
    return get_current_role(request) == "admin"


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

    # Vérifier dans la liste des utilisateurs multi-rôles
    users = cfg.get("users", {})
    role  = None
    if username in users:
        u = users[username]
        if pw_hash == u.get("password_hash"):
            role = u.get("role", "viewer")
    elif username == cfg["username"] and pw_hash == cfg["password_hash"]:
        role = cfg.get("default_role", "admin")

    if role is not None:
        token = secrets.token_hex(32)
        _sessions[token] = {"user": username, "role": role}
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
    cfg   = _load_config()
    users = cfg.get("users", {})
    return {
        "enabled":      cfg["enabled"],
        "username":     cfg["username"],
        "default_role": cfg.get("default_role", "admin"),
        "users":        {u: {"role": d["role"]} for u, d in users.items()},
    }


def update_auth_config(enabled: bool, username: str, password: str | None = None):
    cfg = _load_config()
    cfg["enabled"]  = enabled
    cfg["username"] = username
    if password:
        cfg["password_hash"] = hashlib.sha256(password.encode()).hexdigest()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_auth_config()


def add_user(
    username: str,
    password: str,
    role: str = "operator",
    display_name: str = "",
    email: str = "",
    phone: str = "",
) -> dict:
    """Ajoute un utilisateur avec un rôle et des données personnelles."""
    cfg = _load_config()
    if "users" not in cfg:
        cfg["users"] = {}
    cfg["users"][username] = {
        "password_hash":  hashlib.sha256(password.encode()).hexdigest(),
        "role":           role,
        "display_name":   display_name or username,
        "email":          email,
        "phone":          phone,
    }
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_auth_config()


def update_user_profile(
    username: str,
    display_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
) -> dict:
    """Met à jour le profil d'un utilisateur existant (y compris l'admin principal)."""
    cfg = _load_config()
    users = cfg.get("users", {})
    if username in users:
        u = users[username]
        if display_name is not None: u["display_name"] = display_name
        if email        is not None: u["email"]        = email
        if phone        is not None: u["phone"]        = phone
        if password:                 u["password_hash"] = hashlib.sha256(password.encode()).hexdigest()
    elif username == cfg.get("username"):
        # Admin principal stocké à la racine du config
        if display_name is not None: cfg["display_name"] = display_name
        if email        is not None: cfg["email"]        = email
        if phone        is not None: cfg["phone"]        = phone
        if password:                 cfg["password_hash"] = hashlib.sha256(password.encode()).hexdigest()
    else:
        return {}
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_user_profile(username)


def get_user_profile(username: str) -> dict:
    """Retourne le profil public d'un utilisateur (sans le hash)."""
    cfg   = _load_config()
    users = cfg.get("users", {})
    if username in users:
        u = users[username]
        return {
            "username":     username,
            "display_name": u.get("display_name", username),
            "email":        u.get("email", ""),
            "phone":        u.get("phone", ""),
            "role":         u.get("role", "viewer"),
        }
    # Admin principal
    if username == cfg.get("username"):
        return {
            "username":     username,
            "display_name": cfg.get("display_name", username),
            "email":        cfg.get("email", ""),
            "phone":        cfg.get("phone", ""),
            "role":         cfg.get("default_role", "admin"),
        }
    return {}


def admin_update_user(
    username: str,
    role: str | None = None,
    display_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    password: str | None = None,
) -> dict:
    """Mise à jour complète d'un utilisateur par l'admin (rôle + profil)."""
    cfg = _load_config()
    users = cfg.get("users", {})
    if username not in users:
        return {}
    u = users[username]
    if role         is not None: u["role"]         = role
    if display_name is not None: u["display_name"] = display_name
    if email        is not None: u["email"]        = email
    if phone        is not None: u["phone"]        = phone
    if password:                 u["password_hash"] = hashlib.sha256(password.encode()).hexdigest()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_user_profile(username)


def remove_user(username: str) -> dict:
    """Supprime un utilisateur."""
    cfg = _load_config()
    cfg.get("users", {}).pop(username, None)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_auth_config()
