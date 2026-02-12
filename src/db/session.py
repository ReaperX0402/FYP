from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

def build_engine(echo: bool = False) -> Engine:
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Put in your .env or environment")
    return create_engine(DATABASE_URL, echo= echo, pool_pre_ping= True)

SessionLocal = sessionmaker(autocommit = False, autoflush= False)

def init_session_factory(engine: Engine) -> None:
    SessionLocal.configure(bind = engine)

def db_health_check(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))