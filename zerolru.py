"""zerolru — zero-dependency LRU cache with optional TTL for Python.

Pure standard library. No third-party dependencies. Python 3.11+.

    from zerolru import LRUCache
    c = LRUCache(capacity=128, ttl_seconds=60)
    c.put("k", "v")
    c.get("k")          # -> "v"  (or None if missing/expired)
    "k" in c            # membership (expiry-aware)
    len(c)              # live (non-expired) entry count

Not thread-safe by design: wrap calls in a lock if shared across threads.
See http_server.py for the lock-at-the-edge pattern.
"""
from __future__ import annotations

import time
from collections import OrderedDict, deque
from collections.abc import Callable, Hashable
from typing import Any

__all__ = ["LRUCache"]
__version__ = "0.1.0"


class LRUCache:
    """Bounded, least-recently-used cache with optional per-entry TTL.

    Parameters
    ----------
    capacity:
        Maximum number of entries. Must be a positive integer.
    ttl_seconds:
        If set, entries older than this (by seconds from the injected
        clock) are treated as absent. None disables TTL.
    now:
        Monotonic clock function returning seconds. Injectable so tests
        can advance time deterministically.
    """

    def __init__(
        self,
        capacity: int,
        ttl_seconds: float | None = None,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        if ttl_seconds is not None and ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._now = now
        self._store: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()
        self._expiry: deque[tuple[float, Hashable]] = deque()

    def _expired(self, stamp: float) -> bool:
        return self._ttl is not None and self._now() - stamp > self._ttl

    def _purge(self, key: Hashable) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False
        if self._expired(entry[1]):
            del self._store[key]
            return False
        return True

    def get(self, key: Hashable) -> Any | None:
        """Return value for `key` or None if missing/expired.

        A successful get marks the entry as most-recently-used.
        """
        if not self._purge(key):
            return None
        value = self._store[key][0]
        self._store.move_to_end(key)
        return value

    def put(self, key: Hashable, value: Any) -> None:
        """Insert or update an entry. Updating refreshes recency and TTL."""
        stamp = self._now()
        self._store[key] = (value, stamp)
        self._store.move_to_end(key)
        if self._ttl is not None:
            self._expiry.append((stamp, key))
        while len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        """Number of live (non-expired) entries."""
        if self._ttl is None:
            return len(self._store)
        store = self._store
        exp = self._expiry
        while exp:
            stamp, key = exp[0]
            entry = store.get(key)
            if entry is None or entry[1] != stamp:
                exp.popleft()
                continue
            if self._now() - stamp > self._ttl:
                del store[key]
                exp.popleft()
                continue
            break
        return len(store)

    def __contains__(self, key: object) -> bool:
        return self._purge(key)
