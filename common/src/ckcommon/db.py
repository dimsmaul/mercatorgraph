"""Postgres access: connection pool + a minimal file-based migration runner.

Sync psycopg by design — MCP tools and FastAPI endpoints call these from a threadpool.
No ORM: plain SQL, migrations are ordered ``.sql`` files under ``db/migrations``.
"""

from __future__ import annotations

import os
from pathlib import Path

from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def get_pool(url: str | None = None) -> ConnectionPool:
    """Process-wide singleton connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(url or database_url(), min_size=1, max_size=10, open=True)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


# --- migrations -----------------------------------------------------------

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def apply_migrations(pool: ConnectionPool, migrations_dir: str | Path) -> list[str]:
    """Apply any unapplied ``*.sql`` migrations in filename order.

    Each migration runs in its own transaction; a failure aborts that file and raises.
    Returns the list of filenames applied in this call.
    """
    migrations_dir = Path(migrations_dir)
    files = sorted(migrations_dir.glob("*.sql"))
    applied: list[str] = []

    with pool.connection() as conn:
        conn.execute(_MIGRATIONS_TABLE)
        conn.commit()
        done = {
            row[0]
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }

    for path in files:
        if path.name in done:
            continue
        sql = path.read_text()
        with pool.connection() as conn:
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
                )
        applied.append(path.name)

    return applied
