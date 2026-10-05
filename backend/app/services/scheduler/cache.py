"""Cache of upstream responses, keyed by request (§17).

Several widgets often need the same call: the three Tautulli widgets all read
one `get_activity`, both weather widgets read one forecast. Caching the
*response* rather than the widget data is what makes that collapse into a
single request.

Two widgets due at the same instant would still race, so each key is guarded by
a lock: the first caller performs the request, the others await its result.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)


class SourceCache:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.hits = 0
        self.misses = 0

    async def get_or_collect(
        self, key: str, ttl: int, collect: Callable[[], Awaitable[Any]]
    ) -> Any:
        fresh = self._fresh(key)
        if fresh is not None:
            self.hits += 1
            return fresh[1]

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Another caller may have filled it while we waited.
            fresh = self._fresh(key)
            if fresh is not None:
                self.hits += 1
                return fresh[1]

            self.misses += 1
            value = await collect()
            self._entries[key] = (time.monotonic() + ttl, value)
            return value

    def _fresh(self, key: str) -> tuple[float, Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry[0] <= time.monotonic():
            del self._entries[key]
            return None
        return entry

    def invalidate(self, prefix: str = "") -> None:
        """Drop entries, e.g. after a connector's configuration changed."""
        for key in [k for k in self._entries if k.startswith(prefix)]:
            del self._entries[key]

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()
