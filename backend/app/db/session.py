"""Database session management.

Works with PostgreSQL in production and SQLite in tests. The engine is created
lazily so tests can point DATABASE_URL at a temp SQLite file before import.
"""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def _build_engine() -> Engine:
    url = os.environ.get("DATABASE_URL_OVERRIDE") or get_settings().database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_conn, _record):  # enforce FKs in SQLite tests
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def reset_engine() -> None:
    """Dispose and forget the engine (used by tests when DB URL changes)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
