"""
cache.py
--------
Cache Redis avec fallback dict en mémoire.
Si Redis n'est pas disponible, utilise un dict local (pas de persistance).

Usage:
    from .cache import cache
    cache.set("key", value, ttl=10)
    value = cache.get("key")
"""

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


class _FallbackCache:
    """Cache dict en mémoire avec TTL."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at > 0 and time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        expires_at = time.time() + ttl if ttl > 0 else 0
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def flush(self) -> None:
        self._store.clear()


class CacheClient:
    """
    Client cache unifié : Redis si disponible, fallback dict sinon.
    Les valeurs sont sérialisées en JSON.
    """

    def __init__(self):
        self._redis = None
        self._fallback = _FallbackCache()
        self._try_redis()

    def _try_redis(self):
        try:
            import redis
            r = redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
            r.ping()
            self._redis = r
            logger.info(f"Redis connecté : {REDIS_URL}")
        except Exception as e:
            logger.info(f"Redis non disponible ({e}) — fallback dict")
            self._redis = None

    def get(self, key: str) -> Any | None:
        try:
            if self._redis:
                raw = self._redis.get(key)
                return json.loads(raw) if raw else None
        except Exception:
            self._redis = None
        return self._fallback.get(key)

    def set(self, key: str, value: Any, ttl: int = 60) -> None:
        try:
            if self._redis:
                self._redis.setex(key, ttl, json.dumps(value, default=str))
                return
        except Exception:
            self._redis = None
        self._fallback.set(key, value, ttl)

    def delete(self, key: str) -> None:
        try:
            if self._redis:
                self._redis.delete(key)
                return
        except Exception:
            self._redis = None
        self._fallback.delete(key)

    def flush(self) -> None:
        try:
            if self._redis:
                self._redis.flushdb()
                return
        except Exception:
            self._redis = None
        self._fallback.flush()

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"


# Instance globale
cache = CacheClient()
