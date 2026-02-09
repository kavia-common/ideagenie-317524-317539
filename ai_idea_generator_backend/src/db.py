"""
Database utilities for the AI Idea Generator backend.

We intentionally derive the PostgreSQL connection URL from the source-of-truth
`database/db_connection.txt` file (as required by the project instructions).
That file typically contains a command like:

  psql postgresql://user:pass@host:port/dbname

We parse that and use it to configure SQLAlchemy + psycopg.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_DB_ENGINE: Optional[Engine] = None


def _repo_root() -> Path:
    """Return the repository root directory from the backend container root."""
    # This file lives at: ai_idea_generator_backend/src/db.py
    # repo root is two levels up from ai_idea_generator_backend/
    return Path(__file__).resolve().parents[3]


def _read_db_connection_txt() -> str:
    """Read the PostgreSQL URL from the required db_connection.txt file."""
    db_conn_path = _repo_root() / "ideagenie-317524-317540" / "database" / "db_connection.txt"
    if not db_conn_path.exists():
        raise RuntimeError(
            f"db_connection.txt not found at expected path: {db_conn_path}. "
            "This file is required as the source of truth for DB connectivity."
        )
    raw = db_conn_path.read_text(encoding="utf-8").strip()
    if not raw:
        raise RuntimeError("db_connection.txt is empty; cannot configure database connection.")

    # Expected format: "psql postgresql://...."
    if raw.startswith("psql "):
        return raw.split(" ", 1)[1].strip()

    # Allow raw URL as a fallback format
    if raw.startswith("postgresql://") or raw.startswith("postgres://"):
        return raw

    raise RuntimeError(
        "Unrecognized db_connection.txt format. Expected 'psql postgresql://...' or a raw URL."
    )


# PUBLIC_INTERFACE
def get_engine() -> Engine:
    """Get a singleton SQLAlchemy engine configured from db_connection.txt."""
    global _DB_ENGINE
    if _DB_ENGINE is not None:
        return _DB_ENGINE

    db_url = _read_db_connection_txt()

    # Allow overriding via env var if needed (but db_connection.txt remains source of truth by default).
    db_url = os.getenv("DATABASE_URL", db_url)

    _DB_ENGINE = create_engine(db_url, pool_pre_ping=True)
    return _DB_ENGINE


# PUBLIC_INTERFACE
def init_db() -> None:
    """Initialize required tables if they don't exist.

    We perform minimal DDL at startup to make local/dev and CI environments stable.
    """
    engine = get_engine()
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS ideas (
          id UUID PRIMARY KEY,
          topic TEXT NOT NULL,
          ideas JSONB NOT NULL,
          provider TEXT NOT NULL,
          model TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS idea_shares (
          share_id TEXT PRIMARY KEY,
          idea_id UUID NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_ideas_created_at ON ideas(created_at DESC);",
    ]
    with engine.begin() as conn:
        for stmt in ddl_statements:
            conn.execute(text(stmt))
