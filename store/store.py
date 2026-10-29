"""Thread-safe report stores with a small interchangeable interface."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any


def _plain(value: Any) -> Any:
    """Convert pydantic/dataclass-like reports into JSON-compatible values."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    raise TypeError("report must be a mapping or model with model_dump/dict")


class ReportStore(ABC):
    """Interface for creating, retrieving, updating, and listing reports."""
    @abstractmethod
    def create_report(self, report: dict) -> str:
        """Persist a report and return its identifier."""

    @abstractmethod
    def get_report(self, report_id: str) -> dict | None:
        """Return a report mapping, or None when it does not exist."""

    @abstractmethod
    def update_report(self, report_id: str, patch: dict) -> dict:
        """Merge a patch into a report and return the updated mapping."""

    @abstractmethod
    def list_reports(self, limit: int) -> list[dict]:
        """Return up to limit reports, newest first."""


class MemoryStore(ReportStore):
    """Dictionary-backed, process-local store protected by an RLock."""
    def __init__(self) -> None:
        self._reports: dict[str, dict] = {}
        self._kv: dict[str, Any] = {}
        self._lock = threading.RLock()

    # Simple KV methods for tests
    def create(self, key: str, value: Any) -> None:
        with self._lock:
            self._kv[str(key)] = value

    def get(self, key: str) -> Any:
        with self._lock:
            return self._kv.get(str(key))

    def update(self, key: str, value: Any) -> None:
        with self._lock:
            self._kv[str(key)] = value

    def list(self) -> list[Any]:
        with self._lock:
            return list(self._kv.values())

    # ReportStore interface
    def create_report(self, report: dict) -> str:
        value = dict(_plain(report))
        report_id = str(value.get("id") or uuid.uuid4())
        value["id"] = report_id
        now = time.time()
        value.setdefault("created_at", now)
        value.setdefault("updated_at", now)
        with self._lock:
            self._reports[report_id] = value
        return report_id

    def get_report(self, report_id: str) -> dict | None:
        with self._lock:
            value = self._reports.get(str(report_id))
            return dict(value) if value is not None else None

    def update_report(self, report_id: str, patch: dict) -> dict:
        with self._lock:
            if str(report_id) not in self._reports:
                raise KeyError(report_id)
            value = self._reports[str(report_id)]
            value.update(_plain(patch))
            value["id"] = str(report_id)
            value["updated_at"] = time.time()
            return dict(value)

    def list_reports(self, limit: int) -> list[dict]:
        with self._lock:
            values = sorted(self._reports.values(), key=lambda x: x.get("created_at", 0), reverse=True)
            return [dict(x) for x in values[:max(0, int(limit))]]


class SqliteStore(ReportStore):
    """SQLite JSON store; a configured file path survives process restarts."""
    def __init__(self, path: str | None = None) -> None:
        self.path = path if path is not None else os.environ.get("XC_DB_PATH", ":memory:")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._conn.commit()

    # Simple KV methods for tests
    def create(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (str(key), json.dumps(value)))

    def get(self, key: str) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key=?", (str(key),)).fetchone()
            return json.loads(row["value"]) if row else None

    def update(self, key: str, value: Any) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (str(key), json.dumps(value)))

    def list(self) -> list[Any]:
        with self._lock:
            rows = self._conn.execute("SELECT value FROM kv").fetchall()
            return [json.loads(row["value"]) for row in rows]

    # ReportStore interface
    def create_report(self, report: dict) -> str:
        value = dict(_plain(report))
        report_id = str(value.get("id") or uuid.uuid4())
        value["id"] = report_id
        now = time.time()
        value.setdefault("created_at", now)
        value.setdefault("updated_at", now)
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO reports(id,payload,created_at,updated_at) VALUES(?,?,?,?)", (report_id, json.dumps(value), value["created_at"], value["updated_at"]))
        return report_id

    def get_report(self, report_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM reports WHERE id=?", (str(report_id),)).fetchone()
            return json.loads(row["payload"]) if row else None

    def update_report(self, report_id: str, patch: dict) -> dict:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT payload FROM reports WHERE id=?", (str(report_id),)).fetchone()
            if row is None:
                raise KeyError(report_id)
            value = json.loads(row["payload"])
            value.update(_plain(patch))
            value["id"] = str(report_id)
            value["updated_at"] = time.time()
            self._conn.execute("UPDATE reports SET payload=?,updated_at=? WHERE id=?", (json.dumps(value), value["updated_at"], str(report_id)))
            return value

    def list_reports(self, limit: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM reports ORDER BY created_at DESC LIMIT ?", (max(0, int(limit)),)).fetchall()
            return [json.loads(row["payload"]) for row in rows]

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            self._conn.close()
