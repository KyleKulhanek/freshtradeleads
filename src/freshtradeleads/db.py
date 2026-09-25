from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import database_url


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)

