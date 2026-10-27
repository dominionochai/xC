"""Bounded in-memory replay buffer for one API run."""
from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Any, Deque

REPLAY_BUFFER_SIZE = 5000


class ReplayCursorExpired(ValueError):
    """Raised when the requested cursor predates the retained event window."""


class EventReplayBuffer:
    """Keep the most recent envelopes while preserving monotonic run sequence IDs."""

    def __init__(self, capacity: int = REPLAY_BUFFER_SIZE) -> None:
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self._events: Deque[dict[str, Any]] = deque(maxlen=capacity)
        self._next_seq = 1
        self._lock = RLock()

    def append(self, event_type: str, payload: Any = None) -> dict[str, Any]:
        from .events import event_envelope

        with self._lock:
            event = event_envelope(self._next_seq, event_type, payload)
            self._next_seq += 1
            self._events.append(event)
            return dict(event)

    @property
    def latest_seq(self) -> int:
        with self._lock:
            return self._next_seq - 1

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in self._events]

    def replay_after(self, cursor: int = 0) -> list[dict[str, Any]]:
        if type(cursor) is not int or cursor < 0:
            raise ValueError("cursor must be a non-negative integer")
        with self._lock:
            oldest = self._events[0]["seq"] if self._events else self._next_seq
            latest = self._next_seq - 1
            if cursor > latest:
                raise ValueError("cursor is ahead of the latest event")
            if cursor < oldest - 1:
                raise ReplayCursorExpired("RUN_NOT_RESUMABLE")
            return [dict(event) for event in self._events if event["seq"] > cursor]
