"""Alembic environment.

Two decisions worth stating:

1. **The URL comes from settings.** ``alembic.ini`` has no ``sqlalchemy.url``;
   we read ``get_settings().database_url`` here. One source of truth means a
   migration can never be applied to a different database than the API uses.

2. **``target_metadata`` is the real metadata.** We import the models so
   ``--autogenerate`` sees every table. Importing the API package here would
   drag in FastAPI for no reason, so we import the models module directly.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the repo root importable when Alembic is invoked from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from naijafinsent.config import get_settings  # noqa: E402
from services.api.app.db.base import Base  # noqa: E402
from services.api.app.db import models as _models  # noqa: E402,F401  (registers tables)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the URL: explicit ``-x db_url=...`` override, else settings."""
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    return override or get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # SQLite cannot ALTER most columns; batch mode rewrites the table
            # instead. Harmless on Postgres, essential on SQLite.
            render_as_batch=is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
