"""Per-source rate limiting.

A small, thread-safe helper so plugins can be polite to the services they hit.
``throttle(source, min_interval)`` guarantees at least ``min_interval`` seconds
between successive calls for a given ``source`` (e.g. ``"instagram"``), across
all plugin threads — without blocking calls to *other* sources.

Plugins run concurrently in a thread pool, so this is shared process-wide state
guarded by a per-source lock.
"""

from __future__ import annotations

import threading
import time
from typing import Dict

_registry_lock = threading.Lock()
_locks: Dict[str, threading.Lock] = {}
_last_call: Dict[str, float] = {}


def _lock_for(source: str) -> threading.Lock:
    with _registry_lock:
        return _locks.setdefault(source, threading.Lock())


def throttle(source: str, min_interval: float) -> None:
    """Sleep, if needed, so successive calls for ``source`` are spaced out.

    ``min_interval <= 0`` disables throttling. Only one caller per source waits
    at a time (per-source lock), so unrelated sources are never blocked.
    """
    if min_interval <= 0:
        return
    lock = _lock_for(source)
    with lock:
        now = time.monotonic()
        wait = _last_call.get(source, 0.0) + min_interval - now
        if wait > 0:
            time.sleep(wait)
        _last_call[source] = time.monotonic()
