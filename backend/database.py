"""
Database Engine & Session Factory
=================================
Centralises SQLAlchemy engine creation and provides a FastAPI dependency
for request-scoped sessions.

Supports PostgreSQL for production and SQLite for local development/demo.
Set the ``DATABASE_URL`` environment variable to switch.
"""

from __future__ import annotations

import os

from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Engine configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./ndvi_drone.db",  # default: local SQLite for demos
)

# SQLite requires special args for multi-threaded FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
)


def init_db() -> None:
    """Create all tables defined by SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — yields a request-scoped session."""
    with Session(engine) as session:
        yield session
