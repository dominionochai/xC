"""A small, deterministic, in-memory evidence ledger."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from copy import deepcopy
from typing import Any


class Ledger:
    """Append-only evidence entries protected by a re-entrant thread lock.

    Each entry contains exactly ``index``, ``source``, ``reference``, ``claim``,
    ``previous_hash``, and ``hash``. Hashes are SHA-256 over canonical UTF-8
    JSON of the first five fields, so identical append sequences are identical.
    """

    _GENESIS_HASH = "0" * 64
    _HASH_FIELDS = ("index", "source", "reference", "claim", "previous_hash")
    _ENTRY_FIELDS = frozenset((*_HASH_FIELDS, "hash"))
    _SECRET_LABEL = re.compile(
        r"\b(?:api[_ -]?key|access[_ -]?key|client[_ -]?secret|secret|"
        r"auth(?:orization)?|access[_ -]?token|refresh[_ -]?token|token|"
        r"password|passwd|credential)\b\s*(?::|=|\bis\b)\s*"
        r"[\"']?[^\s,;\"']{3,}",
        re.IGNORECASE,
    )
    _BEARER = re.compile(r"\bbearer\s+[^\s,;]+", re.IGNORECASE)
    _VENDOR_TOKEN = re.compile(
        r"\b(?:sk-(?:live|test)-|sk-|pk_(?:live|test)_|rk_(?:live|test)_|"
        r"gh[pousr]_|ghs_|github_pat_|xox[baprs]-|AKIA|ASIA|AIza|ya29\.|"
        r"hf_|glpat-|npm_|shpat_|SG\.)[A-Za-z0-9._-]{8,}",
        re.IGNORECASE,
    )
    _OPAQUE_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{32,}(?![A-Za-z0-9])")
    _SENTENCE_END = re.compile(r"[.!?]+(?=(?:[\"'”’\)\]]*\s|[\"'”’\)\]]*$))")
    _ABBREVIATIONS = ("mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e")

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._expected_length = 0
        self._lock = threading.RLock()

    @staticmethod
    def _is_json_value(text: str) -> bool:
        """Return whether text parses as JSON (including JSON scalar values)."""
        try:
            json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return False
        return True

    @classmethod
    def _validate_text(cls, field: str, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field} must be a string")
        text = value.strip()
        if not text:
            raise ValueError(f"{field} must not be empty")
        if cls._is_json_value(text):
            raise ValueError(f"{field} must not be a JSON value")
        if (
            cls._SECRET_LABEL.search(text)
            or cls._BEARER.search(text)
            or cls._VENDOR_TOKEN.search(text)
            or cls._OPAQUE_TOKEN.search(text)
        ):
            raise ValueError(f"{field} must not contain credentials or opaque tokens")
        return text

    @classmethod
    def _validate_claim(cls, value: object) -> str:
        claim = cls._validate_text("claim", value)
        endings = list(cls._SENTENCE_END.finditer(claim))
        counted = 0
        for match in endings:
            if match.group(0) == ".":
                prefix = claim[: match.start()].rstrip().lower()
                if (prefix.split() or [''])[-1] in cls._ABBREVIATIONS:
                    continue
            counted += 1
        if counted != 1 or not re.search(r"[.!?][\"'”’\)\]]*\s*$", claim):
            raise ValueError("claim must be exactly one complete sentence")
        return claim

    @classmethod
    def _digest(cls, fields: dict[str, Any]) -> str:
        payload = {name: fields[name] for name in cls._HASH_FIELDS}
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def append(self, source: str, reference: int | str | None, claim: str) -> int:
        """Append a validated entry and return its zero-based index.

        An integer reference must name an already appended entry. String
        references are textual identifiers; ``None`` denotes no reference.
        """
        with self._lock:
            safe_source = self._validate_text("source", source)
            safe_claim = self._validate_claim(claim)
            if reference is None:
                safe_reference: int | str | None = None
            elif type(reference) is int:
                if reference < 0 or reference >= len(self._entries):
                    raise ValueError("integer references must point to an earlier entry")
                safe_reference = reference
            elif isinstance(reference, str):
                safe_reference = self._validate_text("reference", reference)
            else:
                raise TypeError("reference must be an integer, string, or None")

            index = len(self._entries)
            fields: dict[str, Any] = {
                "index": index,
                "source": safe_source,
                "reference": safe_reference,
                "claim": safe_claim,
                "previous_hash": (
                    self._entries[-1]["hash"] if self._entries else self._GENESIS_HASH
                ),
            }
            entry = {**fields, "hash": self._digest(fields)}
            self._entries.append(entry)
            self._expected_length += 1
            return index

    def resolve(self, reference: int) -> dict[str, Any]:
        """Return a defensive copy of an entry addressed by integer index."""
        if type(reference) is not int or reference < 0:
            raise ValueError("reference must be a non-negative integer index")
        with self._lock:
            if reference >= len(self._entries):
                raise ValueError("reference does not identify an existing earlier entry")
            return deepcopy(self._entries[reference])

    @property
    def entries(self) -> list[dict[str, Any]]:
        """Return defensive copies of all entries, in append order."""
        with self._lock:
            return deepcopy(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def verify(self) -> bool:
        """Check expected length, entry shape, references, links, and hashes."""
        with self._lock:
            if len(self._entries) != self._expected_length:
                return False
            previous_hash = self._GENESIS_HASH
            for expected_index, entry in enumerate(self._entries):
                if not isinstance(entry, dict) or set(entry) != self._ENTRY_FIELDS:
                    return False
                if type(entry.get("index")) is not int or entry["index"] != expected_index:
                    return False
                try:
                    self._validate_text("source", entry.get("source"))
                    self._validate_claim(entry.get("claim"))
                    reference = entry.get("reference")
                    if reference is not None:
                        if type(reference) is int:
                            if reference < 0 or reference >= expected_index:
                                return False
                        elif isinstance(reference, str):
                            self._validate_text("reference", reference)
                        else:
                            return False
                except (TypeError, ValueError):
                    return False
                if entry.get("previous_hash") != previous_hash:
                    return False
                try:
                    expected_hash = self._digest(entry)
                except (KeyError, TypeError, ValueError):
                    return False
                if entry.get("hash") != expected_hash:
                    return False
                previous_hash = entry["hash"]
            return True
