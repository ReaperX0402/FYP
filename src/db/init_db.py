from __future__ import annotations

from sqlalchemy import text

from src.db.base import Base, DB_SCHEMA
from src.db.models import (
    Jobs,
    Operators,
    ImportSession,
    Media,
    Decisions,
    Exports,
    LocalArchives,
)


def init_db(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA};"))

    Base.metadata.create_all(bind=engine)