"""Optional async SQLAlchemy persistence for API reports.

SQLAlchemy is imported on first use so importing the existing API does not
require database dependencies to be installed. Configure ``DATABASE_URL``
with an async driver URL (for example, ``postgresql+asyncpg://...``).
"""

from __future__ import annotations

import os
import uuid
from typing import Any


_UNSET = object()
_Base: Any = None
_ReportRecord: Any = None
_async_sessionmaker: Any = None
_create_async_engine: Any = None
_engine: Any = None
_engine_url: str | None = None
_session_factory: Any = None


class DatabaseConfigurationError(RuntimeError):
    """Raised when database dependencies or configuration are unavailable."""


def _load_sqlalchemy() -> None:
    """Load SQLAlchemy and construct mappings only when persistence is used."""
    global _Base, _ReportRecord, _async_sessionmaker, _create_async_engine

    if _Base is not None:
        return

    try:
        from sqlalchemy import DateTime, JSON, String, func
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
    except ImportError as exc:
        raise DatabaseConfigurationError(
            "Report persistence requires SQLAlchemy. Install the project dependencies "
            "(sqlalchemy[asyncio], asyncpg, and alembic)."
        ) from exc

    class Base(DeclarativeBase):
        pass

    class ReportRecord(Base):
        """A persisted report request and its optional result payload."""

        __tablename__ = "reports"

        id: Mapped[str] = mapped_column(
            String(36), primary_key=True, default=lambda: str(uuid.uuid4())
        )
        status: Mapped[str] = mapped_column(
            String(32), nullable=False, default="pending"
        )
        input_data: Mapped[Any] = mapped_column("input", JSON, nullable=False)
        result: Mapped[Any | None] = mapped_column(JSON, nullable=True)
        created_at: Mapped[Any] = mapped_column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        )
        updated_at: Mapped[Any] = mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )

    _Base = Base
    _ReportRecord = ReportRecord
    _async_sessionmaker = async_sessionmaker
    _create_async_engine = create_async_engine


def __getattr__(name: str) -> Any:
    """Expose the mapped classes lazily for migrations and model inspection."""
    if name in {"Base", "ReportRecord"}:
        _load_sqlalchemy()
        return _Base if name == "Base" else _ReportRecord
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseConfigurationError(
            "DATABASE_URL must be set before using report persistence."
        )
    # SQLAlchemy's async engine needs an async PostgreSQL driver explicitly.
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


def get_engine() -> Any:
    """Return the lazily created async engine configured by DATABASE_URL."""
    global _engine, _engine_url, _session_factory
    _load_sqlalchemy()
    url = _database_url()
    if _engine is None or _engine_url != url:
        _engine = _create_async_engine(url, pool_pre_ping=True)
        _engine_url = url
        _session_factory = None
    return _engine


def get_session_factory() -> Any:
    """Return the async session factory bound to the configured engine."""
    global _session_factory
    engine = get_engine()
    if _session_factory is None:
        _session_factory = _async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def create_report(
    input_data: Any,
    *,
    status: str = "pending",
    result: Any = None,
    report_id: str | None = None,
) -> Any:
    """Persist and return a report record."""
    _load_sqlalchemy()
    record = _ReportRecord(status=status, input_data=input_data, result=result)
    if report_id is not None:
        record.id = report_id
    async with get_session_factory()() as session:
        session.add(record)
        await session.commit()
        await session.refresh(record)
    return record


async def get_report(report_id: str) -> Any | None:
    """Fetch a report by its ID, or return ``None`` when it does not exist."""
    _load_sqlalchemy()
    async with get_session_factory()() as session:
        return await session.get(_ReportRecord, report_id)


async def update_report(
    report_id: str,
    *,
    status: str | None = None,
    input_data: Any = _UNSET,
    result: Any = _UNSET,
) -> Any | None:
    """Update supplied report fields and return the record, or ``None``."""
    _load_sqlalchemy()
    async with get_session_factory()() as session:
        record = await session.get(_ReportRecord, report_id)
        if record is None:
            return None
        if status is not None:
            record.status = status
        if input_data is not _UNSET:
            record.input_data = input_data
        if result is not _UNSET:
            record.result = result
        await session.commit()
        await session.refresh(record)
        return record


async def dispose_engine() -> None:
    """Dispose of the current engine, primarily for application shutdown/tests."""
    global _engine, _engine_url, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _engine_url = None
    _session_factory = None
