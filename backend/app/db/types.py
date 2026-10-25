"""Portable primary keys: BIGINT autoincrement on PostgreSQL, INTEGER on SQLite.

SQLite only autoincrements plain INTEGER PRIMARY KEY columns; production uses
BIGSERIAL/BIGINT. The variant keeps both dialects happy.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer
from sqlalchemy.types import TypeEngine

BigIntPK = Integer().with_variant(BigInteger(), "postgresql")
