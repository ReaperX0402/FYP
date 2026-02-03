import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from dotenv import load_dotenv

load_dotenv()

# Alembic Config object
config = context.config

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -------------------------------------------------------
# IMPORT SQLALCHEMY BASE + MODELS HERE
# -------------------------------------------------------
# ✅ CHANGE THESE IMPORTS TO MATCH YOUR PROJECT STRUCTURE
#
# Example A (if your Base is in src/db/base.py and models in src/db/models.py):
# from src.db.base import Base, DB_SCHEMA
# import src.db.models  # noqa: F401
#
# Example B (if your Base is in db/base.py and models in db/models.py):
# from db.base import Base, DB_SCHEMA
# import db.models  # noqa: F401

from src.db.base import Base, DB_SCHEMA   # <-- CHANGE THIS LINE if needed
import src.db.models  # noqa: F401        # <-- CHANGE THIS LINE if needed

target_metadata = Base.metadata


def get_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set. Put it in .env or environment variables.")
    return url


def run_migrations_offline() -> None:
    """Run migrations without connecting to DB (generates SQL scripts)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema=DB_SCHEMA,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # ✅ Ensure schema exists BEFORE tables are created in it
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA};"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=DB_SCHEMA,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

