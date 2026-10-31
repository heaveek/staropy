"""Declarative base with portable type variants.

The project targets PostgreSQL in production (JSONB / timestamptz). For local
tests we keep the same models runnable on SQLite via variant types.
"""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy import JSON, DateTime, String, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Portable JSON: JSONB on PostgreSQL, JSON elsewhere
JsonType = JSON().with_variant(JSONB, "postgresql")

# Portable timezone-aware timestamp: timestamptz on PostgreSQL
TZDateTime = DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "postgresql")


class UUIDType(TypeDecorator):
    """Store UUID as native uuid on PostgreSQL, CHAR(36) string elsewhere."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            value = _uuid.UUID(value)
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return value
        return _uuid.UUID(str(value))
