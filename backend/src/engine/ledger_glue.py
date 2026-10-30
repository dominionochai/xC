"""Optional glue for the evidence ledger implementation."""
from __future__ import annotations

try:
    from backend.methods.evidence import (  # type: ignore
        EvidenceLedgerAdapter,
        make_ledger_entry,
        record_call,
        validate_payload,
    )
except ImportError:  # The evidence package is optional in lightweight installs.
    EvidenceLedgerAdapter = None  # type: ignore[assignment,misc]
    make_ledger_entry = None  # type: ignore[assignment]
    record_call = None  # type: ignore[assignment]
    validate_payload = None  # type: ignore[assignment]


def _entry(kwargs: dict):
    """Build an entry when the evidence package is available, else preserve input."""
    if callable(make_ledger_entry):
        try:
            return make_ledger_entry(**kwargs)
        except TypeError:
            # Support implementations whose factory takes the ledger first.
            return make_ledger_entry(kwargs)
    return dict(kwargs)


def _adapter(ledger):
    if not callable(EvidenceLedgerAdapter):
        return None
    try:
        return EvidenceLedgerAdapter(ledger)
    except TypeError:
        try:
            adapter = EvidenceLedgerAdapter()
            if hasattr(adapter, "ledger"):
                adapter.ledger = ledger
            return adapter
        except TypeError:
            return None


def add_call(ledger, **kwargs):
    """Add one call to a ledger, using the optional evidence helpers if present."""
    if callable(record_call):
        try:
            return record_call(ledger, **kwargs)
        except TypeError:
            entry = _entry(kwargs)
            try:
                return record_call(ledger, entry)
            except TypeError:
                pass

    adapter = _adapter(ledger)
    if adapter is not None:
        for name in ("add_call", "record_call", "append", "add"):
            method = getattr(adapter, name, None)
            if callable(method):
                try:
                    return method(**kwargs)
                except TypeError:
                    try:
                        return method(_entry(kwargs))
                    except TypeError:
                        continue

    entry = _entry(kwargs)
    for name in ("add_call", "record_call", "append", "add"):
        method = getattr(ledger, name, None)
        if callable(method):
            try:
                return method(**kwargs)
            except TypeError:
                return method(entry)
    if isinstance(ledger, list):
        ledger.append(entry)
        return entry
    return entry


def _valid(result) -> bool:
    if isinstance(result, tuple) and result:
        return bool(result[0])
    if isinstance(result, dict):
        for key in ("valid", "ok", "success"):
            if key in result:
                return bool(result[key])
    return bool(result)


def verify(ledger) -> bool:
    """Return whether the optional validator or ledger accepts its contents."""
    adapter = _adapter(ledger)
    if adapter is not None:
        for name in ("verify", "validate", "validate_payload"):
            method = getattr(adapter, name, None)
            if callable(method):
                try:
                    return _valid(method())
                except TypeError:
                    try:
                        return _valid(method(ledger))
                    except TypeError:
                        continue

    method = getattr(ledger, "verify", None)
    if callable(method):
        try:
            return _valid(method())
        except TypeError:
            return _valid(method(ledger))

    if callable(validate_payload):
        try:
            return _valid(validate_payload(ledger))
        except (TypeError, ValueError):
            return False
    return False
