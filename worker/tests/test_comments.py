import os
from pathlib import Path

import pytest

from ckcommon.db import apply_migrations
from ckworker.comments import add_comment, list_comments, set_status

REPO_ROOT = Path(__file__).resolve().parents[1].parent
MIGRATIONS = REPO_ROOT / "db" / "migrations"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


@pytest.fixture
def pool():
    from psycopg_pool import ConnectionPool

    p = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=4, open=True)
    with p.connection() as conn:
        conn.execute(
            "DROP TABLE IF EXISTS annotations, audit_log, tokens, builds, projects, "
            "schema_migrations CASCADE"
        )
        conn.commit()
    apply_migrations(p, MIGRATIONS)
    with p.connection() as conn:
        for slug in ("a", "b"):
            conn.execute(
                "INSERT INTO projects (slug, repo_url) VALUES (%s, %s)",
                (slug, f"https://x/{slug}.git"),
            )
        conn.commit()
    yield p
    p.close()


def test_add_list_and_status(pool):
    cid = add_comment(pool, "a", "n1", "why?", "dev")
    got = list_comments(pool, "a", "n1")
    assert got[0]["id"] == cid
    assert got[0]["status"] == "open"
    assert set_status(pool, "a", cid, "resolved") is True
    assert list_comments(pool, "a", "n1")[0]["status"] == "resolved"


def test_invalid_status_raises(pool):
    cid = add_comment(pool, "a", "n1", "x", "dev")
    with pytest.raises(ValueError):
        set_status(pool, "a", cid, "bogus")


def test_set_status_is_project_scoped(pool):
    """Cross-tenant guard: project b cannot change project a's comment (IDOR fix)."""
    cid = add_comment(pool, "a", "n1", "secret", "dev")
    # wrong project -> no update
    assert set_status(pool, "b", cid, "resolved") is False
    # unchanged
    assert list_comments(pool, "a", "n1")[0]["status"] == "open"
    # correct project -> updates
    assert set_status(pool, "a", cid, "resolved") is True
