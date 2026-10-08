"""Remembers recent things by id for a few minutes: reply texts to speak, and rendered songs.

The page only ever gets an id, never a "speak any text" door, so nobody can use the
server to spend ElevenLabs credits on their own words.
"""

import secrets
import threading
import time
from collections import OrderedDict
from typing import Any

KEEP_SECONDS = 300


class ShortTermStore:
    def __init__(self, keep_at_most: int, clock=time.monotonic):
        self._keep_at_most = keep_at_most
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, value: Any) -> str:
        item_id = secrets.token_urlsafe(12)
        with self._lock:
            self._items[item_id] = (self._clock(), value)
            self._forget_old()
        return item_id

    def get(self, item_id: str) -> Any | None:
        with self._lock:
            self._forget_old()
            saved = self._items.get(item_id)
        return saved[1] if saved else None

    def _forget_old(self) -> None:
        oldest_allowed = self._clock() - KEEP_SECONDS
        while self._items and (len(self._items) > self._keep_at_most or next(iter(self._items.values()))[0] < oldest_allowed):
            self._items.popitem(last=False)
