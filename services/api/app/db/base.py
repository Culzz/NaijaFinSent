"""SQLAlchemy 2.0 engine, session factory, declarative base and FastAPI dependency.

Design notes
------------
* One ``Settings.database_url`` drives everything, so the same code runs on
  SQLite (dev/test) and Postgres (prod). We only branch on the dialect for the
  handful of things SQLite genuinely cannot do.
* ``pool_pre_ping=True`` everywhere: managed Postgres (Railway/Fly/RDS) drops
  idle connections, and a stale connection surfacing as a 500 on the first
  request after a quiet period is a classic production papercut.
* SQLite gets ``check_same_thread=False`` because FastAPI runs sync endpoint
  handlers in a threadpool, so a session created on one thread can be used on
  another. That is safe here because each request gets its own session.
* ``init_db()`` is a dev/test convenience only. Production schema changes go
  through Alembic (``services/api/alembic``), never through ``create_all``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from naijafinsent.config import get_settings
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base shared by every model in :mod:`services.api.app.db.models`."""

    # Keeps ``repr()`` output readable when debugging without pulling in the
    # whole column list for wide tables.
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} id={pk!r}>"


def _ensure_sqlite_parent(url: URL) -> None:
    """Create the containing directory for a file-backed SQLite URL.

    ``sqlite:///./data/naijafinsent.db`` fails with an opaque
    ``unable to open database file`` if ``./data`` does not exist, which is a
    confusing first-run experience. We create it instead.
    """
    database = url.database
    if not database or database == ":memory:":
        return
    parent = Path(database).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)


def _is_sqlite(url: URL) -> bool:
    return url.get_backend_name() == "sqlite"


def build_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """Build an :class:`~sqlalchemy.Engine` for SQLite or Postgres.

    Parameters
    ----------
    database_url:
        Overrides ``settings.database_url``. Tests pass a tmp-path SQLite URL.
    echo:
        SQL echo. Off by default; turn on for a single debugging session.
    """
    url = make_url(database_url or get_settings().database_url)
    sqlite = _is_sqlite(url)

    if sqlite:
        _ensure_sqlite_parent(url)

    connect_args: dict[str, Any] = {}
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True, "echo": echo}

    if sqlite:
        # See module docstring: sessions cross threadpool threads per request.
        connect_args["check_same_thread"] = False
        # A single-file SQLite DB does not benefit from SQLAlchemy's default
        # QueuePool sizing and it trips up tests that want a clean file.
        kwargs["poolclass"] = __import__(
            "sqlalchemy.pool", fromlist=["NullPool"]
        ).NullPool
    else:
        # Postgres: recycle before typical managed-provider idle timeouts.
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_recycle"] = 1800

    kwargs["connect_args"] = connect_args
    engine = create_engine(url, **kwargs)

    if sqlite:
        _install_sqlite_pragmas(engine)

    return engine


def _install_sqlite_pragmas(engine: Engine) -> None:
    """Turn on foreign keys (off by default in SQLite) and WAL.

    Without ``PRAGMA foreign_keys=ON`` every ``ON DELETE`` clause in our models
    is silently ignored under SQLite, which would make the repository tests lie.
    """

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _record: Any) -> None:  # noqa: ANN401
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


# --------------------------------------------------------------------------
# Process-wide engine / session factory
# --------------------------------------------------------------------------
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the lazily-created process-wide engine."""
    global _engine
    if _engine is None:
        _engine = build_engine()
        logger.info("database engine created: %s", _engine.url.render_as_string(False))
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the lazily-created process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _session_factory


def reset_engine_state(
    *, engine: Engine | None = None, session_factory: sessionmaker[Session] | None = None
) -> None:
    """Override the global engine/session factory. Tests and the app factory use this."""
    global _engine, _session_factory
    if engine is not None:
        _engine = engine
    if session_factory is not None:
        _session_factory = session_factory
    if engine is not None and session_factory is None:
        _session_factory = sessionmaker(
            bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
        )


def init_db(*, engine: Engine | None = None, drop_first: bool = False) -> Engine:
    """Create all tables.

    **Dev/test only.** Production uses the Alembic migrations under
    ``services/api/alembic`` so that schema evolution is reviewable and reversible.

    ``drop_first`` exists for tests that want a pristine file each session.
    """
    # Import for the side effect of registering every model on ``Base.metadata``.
    from services.api.app.db import models as _models  # noqa: F401

    target = engine or get_engine()
    if drop_first:
        Base.metadata.drop_all(bind=target)
    Base.metadata.create_all(bind=target)
    return target


def session_scope(engine: Engine | None = None) -> Session:
    """Open a session for non-request contexts (worker, scripts, repositories).

    Callers own the lifecycle and must ``commit``/``rollback``/``close``.
    """
    if engine is not None:
        return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return get_session_factory()()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session.

    The session is closed in a ``finally`` block, so an exception anywhere in the
    request still releases the connection back to the pool.
    """
    session = session_scope()
    try:
        yield session
    finally:
        session.close()


def check_connection(engine: Engine | None = None) -> tuple[bool, str]:
    """Cheap liveness probe used by ``GET /health``.

    Returns ``(ok, detail)`` rather than raising, because health checks must
    never turn a degraded dependency into a crash-looping container.
    """
    target = engine or get_engine()
    try:
        with target.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - health checks report, never raise
        logger.warning("database health check failed: %r", exc)
        return False, f"error: {type(exc).__name__}"
