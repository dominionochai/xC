"""Thread-safe, in-memory event bus for a single run."""

from collections import deque
import json
import threading
import time


RESUME_BUFFER_SIZE = 5000
_MAX_PREVIEW_BYTES = 2 * 1024


class EventBus:
    """Store a bounded stream of run events without writing to disk."""

    def __init__(self):
        self._lock = threading.Lock()
        self._events = deque(maxlen=RESUME_BUFFER_SIZE)
        self._next_seq = 1
        self._cancelled = False

    def emit(self, event_type, payload=None):
        """Record and return an event, truncating its JSON payload preview to 2 KB."""
        preview = json.dumps(payload)
        # json.dumps defaults to ASCII escaping, so character and byte counts match.
        preview = preview[:_MAX_PREVIEW_BYTES]
        with self._lock:
            event = {
                "seq": self._next_seq,
                "type": event_type,
                "ts": time.time(),
                "payload_preview": preview,
            }
            self._next_seq += 1
            self._events.append(event)
            return dict(event)

    def cancel(self):
        """Mark this run as cancelled."""
        with self._lock:
            self._cancelled = True

    def is_cancelled(self):
        """Return whether this run has been cancelled."""
        with self._lock:
            return self._cancelled

    def get_run_events(self):
        """Return a snapshot of the events currently retained in the ring buffer."""
        with self._lock:
            return [dict(event) for event in self._events]

    def reset(self):
        """Start a fresh run, resetting sequence, events, and cancellation state."""
        with self._lock:
            self._events.clear()
            self._next_seq = 1
            self._cancelled = False

    def keepalive_comments(self, interval_s=10):
        """Yield SSE keepalive comments and emit matching events at each interval."""
        if interval_s <= 0:
            raise ValueError("interval_s must be greater than zero")
        while not self.is_cancelled():
            time.sleep(interval_s)
            if self.is_cancelled():
                return
            comment = ": keepalive"
            self.emit("keepalive", comment)
            yield comment + "\n\n"
