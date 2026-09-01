"""SQLite lifecycle and caller-owned SQLAlchemy sessions."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import Config


def _database_url(path: str) -> str:
    if path == ":memory:":
        return "sqlite://"
    return f"sqlite:///{Path(path).resolve()}"


def _make_engine(path: str):
    options = {
        "future": True,
        "connect_args": {"check_same_thread": False, "timeout": 15},
    }
    if path == ":memory:":
        options["poolclass"] = StaticPool
    created = create_engine(_database_url(path), **options)

    @event.listens_for(created, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
        if path != ":memory:":
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return created


DATABASE_PATH = Config.DATABASE_PATH
engine = _make_engine(DATABASE_PATH)
session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
Session = scoped_session(session_factory)


def configure_database(path: str) -> None:
    """Rebind database resources; primarily used by the app factory and tests."""
    global DATABASE_PATH, engine, session_factory, Session
    Session.remove()
    engine.dispose()
    DATABASE_PATH = path
    if path != ":memory:":
        Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = _make_engine(path)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    Session = scoped_session(session_factory)


def get_session():
    """Return the request/thread scoped session; the caller owns commit/rollback."""
    return Session()


@contextmanager
def serialized_session():
    """Open one serialized SQLite write transaction.

    `BEGIN IMMEDIATE` obtains SQLite's write reservation before any balance,
    approval, or audit-chain state is read. Every helper receives this session
    and may flush, but only this context commits.
    """
    session = session_factory()
    try:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def initialize_database(*, seed_policies: bool = True) -> None:
    """Create the schema explicitly. User credentials are never seeded here."""
    from src.models import Base

    if DATABASE_PATH != ":memory:":
        Path(DATABASE_PATH).resolve().parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    if seed_policies:
        seed_default_policies()


def seed_default_policies() -> None:
    from src.models import Policy
    from src.policy import DEFAULT_POLICIES, encode_policy_value

    with serialized_session() as session:
        for key, spec in DEFAULT_POLICIES.items():
            if session.query(Policy).filter_by(key=key).first() is None:
                value, value_type = encode_policy_value(spec.default, spec.value_type)
                session.add(Policy(
                    key=key,
                    value=value,
                    type=value_type,
                    description=spec.description,
                    active=True,
                ))


def check_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# Compatibility aliases retained for existing scripts/routes.
initialize_database = initialize_database
seed_default_policies = seed_default_policies


def reset_database() -> None:
    if os.getenv("ALLOW_DESTRUCTIVE_DEV_TOOLS") != "I_UNDERSTAND_DATA_WILL_BE_DELETED":
        raise RuntimeError("Destructive reset is disabled")
    from src.models import Base
    Base.metadata.drop_all(engine)
    initialize_database()

