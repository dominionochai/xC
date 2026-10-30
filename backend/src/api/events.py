"""SSE event envelope and wire-format helpers."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

_EVENT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def event_envelope(seq: int, event_type: str, payload: Any = None) -> dict[str, Any]:
    """Create the stable JSON envelope used in every sequenced stream frame."""
    if type(seq) is not int or seq < 1:
        raise ValueError("seq must be a positive integer")
    if not isinstance(event_type, str) or not _EVENT_NAME.fullmatch(event_type):
        raise ValueError("event_type contains invalid SSE characters")
    return {"id": seq, "seq": seq, "type": event_type, "data": payload}


def encode_sse(event_type: str, envelope: Mapping[str, Any]) -> str:
    """Encode one SSE event; the JSON envelope's id is also the SSE id."""
    seq = envelope.get("seq")
    if type(seq) is not int or seq < 1 or envelope.get("id") != seq:
        raise ValueError("SSE envelope id must equal its positive seq")
    if envelope.get("type") != event_type or not _EVENT_NAME.fullmatch(event_type):
        raise ValueError("event type does not match envelope")
    data = json.dumps(dict(envelope), ensure_ascii=False, separators=(",", ":"))
    return f"id: {seq}\nevent: {event_type}\ndata: {data}\n\n"


def encode_comment(text: str = "keepalive") -> str:
    """Encode an SSE comment (comments never consume an event sequence)."""
    safe = str(text).replace("\r", " ").replace("\n", " ")
    return f": {safe}\n\n"
