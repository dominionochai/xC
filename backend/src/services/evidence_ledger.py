"""Append-only, hash-chained storage for JSON-compatible evidence records.

Each record is hashed as UTF-8 canonical JSON: keys are sorted, separators are
compact, Unicode is preserved, and non-finite numbers are rejected. The
``current_hash`` field itself is excluded from the record being hashed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


_REQUIRED_FIELDS = (
    "index",
    "timestamp",
    "source",
    "reference",
    "claim",
    "payload",
    "previous_hash",
    "current_hash",
)


def _validate_json_value(value: Any, path: str = "$root") -> None:
    """Reject Python values that do not have an unambiguous JSON encoding."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path} is not valid canonical JSON")
        return
    if isinstance(value, list):
        for position, item in enumerate(value):
            _validate_json_value(item, f"{path}[{position}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"object key at {path} must be a string")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise TypeError(f"value at {path} is not JSON-compatible: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a JSON value deterministically for hashing."""
    _validate_json_value(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def hash_evidence_record(record: Mapping[str, Any]) -> str:
    """Return the SHA-256 digest of a record, excluding ``current_hash``."""
    body = {key: value for key, value in record.items() if key != "current_hash"}
    serialized = canonical_json(body).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _verification_failure(
    message: str, index: int | None, checked: int, total: int
) -> dict[str, Any]:
    return {
        "valid": False,
        "records_checked": checked,
        "record_count": total,
        "error": message,
        "index": index,
    }


def verify_evidence_chain(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate record shape, sequential indices, links, and SHA-256 hashes.

    The returned report has ``valid``, ``records_checked``, ``record_count``,
    ``error``, and ``index`` keys. An empty chain is valid.
    """
    try:
        chain = list(records)
    except TypeError as error:
        return _verification_failure(f"records are not iterable: {error}", None, 0, 0)

    previous_hash: str | None = None
    checked = 0
    for expected_index, candidate in enumerate(chain):
        if not isinstance(candidate, Mapping):
            return _verification_failure(
                "record must be a mapping", expected_index, checked, len(chain)
            )
        record = dict(candidate)
        missing = [field for field in _REQUIRED_FIELDS if field not in record]
        if missing:
            return _verification_failure(
                f"record is missing required fields: {', '.join(missing)}",
                expected_index,
                checked,
                len(chain),
            )
        if isinstance(record["index"], bool) or not isinstance(record["index"], int):
            return _verification_failure(
                "record index must be an integer", expected_index, checked, len(chain)
            )
        if record["index"] != expected_index:
            return _verification_failure(
                f"expected index {expected_index}, got {record['index']}",
                expected_index,
                checked,
                len(chain),
            )
        for field in ("timestamp", "source", "reference", "claim"):
            if not isinstance(record[field], str):
                return _verification_failure(
                    f"{field} must be a string", expected_index, checked, len(chain)
                )
        if record["previous_hash"] != previous_hash:
            return _verification_failure(
                "previous_hash does not link to the preceding record",
                expected_index,
                checked,
                len(chain),
            )
        current_hash = record["current_hash"]
        if not isinstance(current_hash, str):
            return _verification_failure(
                "current_hash must be a string", expected_index, checked, len(chain)
            )
        try:
            expected_hash = hash_evidence_record(record)
        except (TypeError, ValueError, OverflowError) as error:
            return _verification_failure(
                f"record cannot be canonically serialized: {error}",
                expected_index,
                checked,
                len(chain),
            )
        if not hmac.compare_digest(current_hash, expected_hash):
            return _verification_failure(
                "current_hash does not match record contents",
                expected_index,
                checked,
                len(chain),
            )
        previous_hash = current_hash
        checked += 1

    return {
        "valid": True,
        "records_checked": checked,
        "record_count": len(chain),
        "error": None,
        "index": None,
    }


class XcEvidenceLedger:
    """In-memory append-only evidence ledger with a verifiable hash chain."""

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    @property
    def records(self) -> list[dict[str, Any]]:
        """Return a defensive copy so callers cannot mutate the stored chain."""
        return deepcopy(self._records)

    def append(
        self,
        source: str,
        reference: str,
        claim: str,
        payload: Any,
        *,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Append an evidence record and return a defensive copy of it.

        ``timestamp`` may be supplied for imports or reproducible use; otherwise
        the current UTC time is stored in ISO 8601 format with a ``Z`` suffix.
        """
        for field, value in (("source", source), ("reference", reference), ("claim", claim)):
            if not isinstance(value, str):
                raise TypeError(f"{field} must be a string")
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            )
        elif not isinstance(timestamp, str):
            raise TypeError("timestamp must be a string")

        record: dict[str, Any] = {
            "index": len(self._records),
            "timestamp": timestamp,
            "source": source,
            "reference": reference,
            "claim": claim,
            "payload": deepcopy(payload),
            "previous_hash": self._records[-1]["current_hash"] if self._records else None,
        }
        # Validate the complete record before mutating the ledger.
        canonical_json(record)
        record["current_hash"] = hash_evidence_record(record)
        self._records.append(record)
        return deepcopy(record)

    def verify(self) -> dict[str, Any]:
        """Return a validation report for this ledger's current chain."""
        return verify_evidence_chain(self._records)
