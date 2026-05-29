"""
backup.py
---------
Sauvegarde automatique de la base SQLite via sqlite3.backup().
Conserve les N dernières sauvegardes (rotation).
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Répertoire de sauvegarde par défaut
DEFAULT_BACKUP_DIR = Path(__file__).parent.parent.parent / "backups"


def run_backup(
    db_path: str | Path | None = None,
    backup_dir: str | Path | None = None,
    keep: int = 24,
) -> str | None:
    """
    Crée une sauvegarde SQLite horodatée et supprime les plus anciennes.

    Parameters
    ----------
    db_path : chemin vers alerts.db (auto-détecté si None)
    backup_dir : dossier de destination (défaut : ./backups)
    keep : nombre de sauvegardes à conserver (défaut 24)

    Returns
    -------
    Chemin du fichier créé, ou None en cas d'erreur.
    """
    if db_path is None:
        db_path = Path(__file__).parent.parent.parent / "alerts.db"
    db_path = Path(db_path)

    if not db_path.exists():
        logger.warning(f"backup: base introuvable {db_path}")
        return None

    if backup_dir is None:
        backup_dir = DEFAULT_BACKUP_DIR
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"alerts_{ts}.db"

    try:
        src  = sqlite3.connect(str(db_path))
        dst  = sqlite3.connect(str(dest))
        src.backup(dst)
        dst.close()
        src.close()
        logger.info(f"Backup créé : {dest}")
    except Exception as e:
        logger.error(f"Backup échoué : {e}")
        return None

    # Rotation : supprimer les plus anciennes
    _rotate(backup_dir, keep)
    return str(dest)


def list_backups(backup_dir: str | Path | None = None) -> list[dict]:
    """Retourne la liste des sauvegardes disponibles (les plus récentes d'abord)."""
    if backup_dir is None:
        backup_dir = DEFAULT_BACKUP_DIR
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []

    files = sorted(backup_dir.glob("alerts_*.db"), reverse=True)
    result = []
    for f in files:
        stat = f.stat()
        result.append({
            "filename": f.name,
            "path":     str(f),
            "size_kb":  round(stat.st_size / 1024, 1),
            "created":  datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return result


def _rotate(backup_dir: Path, keep: int):
    """Supprime les sauvegardes excédentaires."""
    files = sorted(backup_dir.glob("alerts_*.db"))
    while len(files) > keep:
        oldest = files.pop(0)
        try:
            oldest.unlink()
            logger.debug(f"Ancienne sauvegarde supprimée : {oldest.name}")
        except Exception as e:
            logger.warning(f"Impossible de supprimer {oldest}: {e}")
