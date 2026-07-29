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
    with p.connection() as conn:
        conn.execute(
            "DROP TABLE IF EXISTS annotations, audit_log, tokens, builds, projects, "
            "schema_migrations CASCADE"
        )
        conn.commit()
    apply_migrations(p, MIGRATIONS)
    with p.connection() as conn:
        conn.execute(
            "INSERT INTO projects (slug, repo_url) VALUES ('demo','https://x/demo.git')"
        )
        conn.commit()
    yield p
    p.close()


def test_annotations_index_exists(pool):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='annotations'"
        ).fetchall()
    assert "annotations_project_node_idx" in {r[0] for r in rows}


# --- Task 2: repository ---------------------------------------------------
from ckmcp.annotations import (  # noqa: E402
    add_annotation,
    annotation_counts,
    annotations_for_nodes,
)


def test_add_and_read_annotation(pool):
    aid = add_annotation(pool, "demo", "svc_db_conn", "why singleton?", "dev-1")
    assert isinstance(aid, int)
    by_node = annotations_for_nodes(pool, "demo", ["svc_db_conn"])
    items = by_node["svc_db_conn"]
    assert len(items) == 1
    a = items[0]
    assert a["content"] == "why singleton?"
    assert a["principal"] == "dev-1"
    assert a["status"] == "open"
    assert a["tag"] == "CONTRIBUTED"


def test_annotations_for_unknown_node_is_empty(pool):
    assert annotations_for_nodes(pool, "demo", ["nope"]) == {}


def test_annotation_counts(pool):
    add_annotation(pool, "demo", "n1", "a", "dev")
    add_annotation(pool, "demo", "n1", "b", "dev")
    add_annotation(pool, "demo", "n2", "c", "dev")
    counts = annotation_counts(pool, "demo", ["n1", "n2", "n3"])
    assert counts == {"n1": 2, "n2": 1}
