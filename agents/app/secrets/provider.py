"""The ``SecretsProvider`` seam: resolve a secret by name, just-in-time, from whatever backend
is configured (env / AWS / Azure — see ``env_provider.py``/``aws_provider.py``/``azure_provider.py``
and ``factory.py``). A thin resolver, not a framework: no policy, no rotation scheduler, just a
short in-memory cache per name with a force-refresh escape hatch so a rotated secret is picked up
without a rebuild/restart.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod


class SecretNotFoundError(KeyError):
    """No value is resolvable for this secret name under the configured backend."""


class SecretsProvider(ABC):
    @abstractmethod
    def get(self, name: str, *, force_refresh: bool = False) -> str:
        """Return the current value of secret ``name``.

        Cached for a short TTL after the first successful read; pass ``force_refresh=True`` (or
        call :meth:`invalidate` first) to skip the cache and re-read from the backend — the path
        a rotated secret needs, with no process restart. Raises :class:`SecretNotFoundError` if
        the backend has no value for ``name``.
        """

    @abstractmethod
    def invalidate(self, name: str | None = None) -> None:
        """Drop the cached value for ``name`` (or every cached value when ``name`` is ``None``)
        so the next :meth:`get` call re-reads from the backend."""


class CachingSecretsProvider(SecretsProvider):
    """Shared short-TTL in-memory cache every backend wraps its real fetch in. A cache hit within
    ``ttl_seconds`` of the last successful fetch skips the backend call entirely.

    Subclasses implement :meth:`_fetch` only — the actual per-backend read — and never call it
    directly; always go through :meth:`get`.
    """

    def __init__(self, *, ttl_seconds: float = 300.0) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[str, float]] = {}

    def get(self, name: str, *, force_refresh: bool = False) -> str:
        now = time.monotonic()
        if not force_refresh:
            cached = self._cache.get(name)
            if cached is not None:
                value, fetched_at = cached
                if now - fetched_at < self._ttl_seconds:
                    return value
        value = self._fetch(name)
        self._cache[name] = (value, now)
        return value

    def invalidate(self, name: str | None = None) -> None:
        if name is None:
            self._cache.clear()
        else:
            self._cache.pop(name, None)

    @abstractmethod
    def _fetch(self, name: str) -> str:
        """Backend-specific read. Raise :class:`SecretNotFoundError` if ``name`` is unset."""
