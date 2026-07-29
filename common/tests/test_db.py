"""DB + migration tests. Skipped unless DATABASE_URL points at a reachable Postgres."""

import os
from pathlib import Path

import pytest

from ckcommon.db import apply_migrations

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "db" / "migrations"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


@pytest.fixture
def pool():
    from psycopg_pool import ConnectionPool

    p = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=4, open=True)
    # clean slate
    with p.connection() as conn:
        conn.execute(
            "DROP TABLE IF EXISTS annotations, audit_log, tokens, builds, projects, "
            "schema_migrations CASCADE"
        )
        conn.commit()
    yield p
    p.close()


def test_migrations_apply_once_and_are_idempotent(pool):
    applied = apply_migrations(pool, MIGRATIONS)
    assert "001_init.sql" in applied
    # second run applies nothing
    assert apply_migrations(pool, MIGRATIONS) == []


def test_tables_exist_after_migration(pool):
    apply_migrations(pool, MIGRATIONS)
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"projects", "builds", "tokens", "audit_log", "annotations"} <= names


def test_project_and_build_roundtrip(pool):
    apply_migrations(pool, MIGRATIONS)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO projects (slug, repo_url) VALUES (%s, %s)",
            ("demo", "https://example.com/demo.git"),
        )
        conn.execute(
            "INSERT INTO builds (project_slug, version_ts, status, node_count, edge_count) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("demo", "20260728T000000", "succeeded", 9, 18),
        )
        conn.commit()
        row = conn.execute(
            "SELECT status, node_count, edge_count FROM builds WHERE project_slug=%s",
            ("demo",),
        ).fetchone()
    assert row == ("succeeded", 9, 18)
