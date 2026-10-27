"""Small, dependency-light support primitives for the public API."""

from .events import encode_comment, encode_sse, event_envelope
from .resume import EventReplayBuffer, ReplayCursorExpired, REPLAY_BUFFER_SIZE

__all__ = [
    "EventReplayBuffer",
    "ReplayCursorExpired",
    "REPLAY_BUFFER_SIZE",
    "encode_comment",
    "encode_sse",
    "event_envelope",
]
