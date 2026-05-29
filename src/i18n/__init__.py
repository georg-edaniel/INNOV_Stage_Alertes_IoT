"""
i18n/__init__.py
----------------
Système de traduction FR/EN simple basé sur des fichiers JSON.

Usage dans les templates Jinja2 :
    {{ _('nav.dashboard') }}
    {{ _('alerts.title') }}

Usage Python :
    from src.i18n import get_translator
    _ = get_translator("fr")
    print(_("nav.dashboard"))  # → "Tableau de bord"
"""

import json
import logging
from pathlib import Path
from fastapi import Request

logger = logging.getLogger(__name__)

_I18N_DIR = Path(__file__).parent
_translations: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    """Charge le fichier JSON de traduction pour une langue."""
    if lang in _translations:
        return _translations[lang]
    path = _I18N_DIR / f"{lang}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _translations[lang] = data
            return data
        except Exception as e:
            logger.warning(f"i18n: impossible de charger {path}: {e}")
    _translations[lang] = {}
    return {}


def translate(key: str, lang: str = "fr") -> str:
    """Traduit une clé dans la langue spécifiée. Retourne la clé si non trouvée."""
    data = _load(lang)
    if key in data:
        return data[key]
    # Fallback FR
    if lang != "fr":
        fr = _load("fr")
        if key in fr:
            return fr[key]
    return key


def get_lang(request: Request) -> str:
    """Extrait la langue préférée depuis le cookie 'lang' (défaut: fr)."""
    lang = request.cookies.get("lang", "fr")
    return lang if lang in ("fr", "en") else "fr"


def get_translator(lang: str = "fr"):
    """Retourne une fonction de traduction pour la langue spécifiée."""
    def _(key: str) -> str:
        return translate(key, lang)
    return _


def make_jinja_context(request: Request) -> dict:
    """
    Retourne le contexte Jinja2 pour i18n.
    Ajoute _ (fonction de traduction) et lang (langue courante).
    """
    lang = get_lang(request)
    return {
        "_":    get_translator(lang),
        "lang": lang,
    }
