import os
from pathlib import Path

import pytest

from ckcommon.db import apply_migrations
from ckmcp.auth import (
    TokenInfo,
    allowed_projects,
    audit,
    check_scope,
    hash_token,
    lookup_token,
)

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
        for slug in ("a", "b"):
            conn.execute(
                "INSERT INTO projects (slug, repo_url) VALUES (%s, %s)",
                (slug, f"https://example.com/{slug}.git"),
            )
        conn.execute(
            "INSERT INTO tokens (token_hash, principal, scopes) VALUES (%s, %s, %s)",
            (hash_token("tok-a"), "agent-a", ["a"]),
        )
        conn.execute(
            "INSERT INTO tokens (token_hash, principal, scopes) VALUES (%s, %s, %s)",
            (hash_token("tok-all"), "agent-super", ["*"]),
        )
        conn.commit()
    yield p
    p.close()


def test_hash_is_stable_and_not_plaintext():
    h = hash_token("secret")
    assert h == hash_token("secret")
    assert "secret" not in h
    assert len(h) == 64  # sha256 hex


def test_lookup_valid_token(pool):
    info = lookup_token(pool, "tok-a")
    assert isinstance(info, TokenInfo)
    assert info.principal == "agent-a"
    assert info.scopes == ["a"]


def test_lookup_invalid_token(pool):
    assert lookup_token(pool, "nope") is None


def test_lookup_updates_last_used(pool):
    lookup_token(pool, "tok-a")
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT last_used_at FROM tokens WHERE principal=%s", ("agent-a",)
        ).fetchone()
    assert row[0] is not None


def test_expired_token_rejected(pool):
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO tokens (token_hash, principal, scopes, expires_at) "
            "VALUES (%s, %s, %s, now() - interval '1 hour')",
            (hash_token("tok-expired"), "agent-x", ["a"]),
        )
        conn.commit()
    assert lookup_token(pool, "tok-expired") is None


def test_future_expiry_accepted(pool):
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO tokens (token_hash, principal, scopes, expires_at) "
            "VALUES (%s, %s, %s, now() + interval '1 hour')",
            (hash_token("tok-future"), "agent-y", ["a"]),
        )
        conn.commit()
    info = lookup_token(pool, "tok-future")
    assert info is not None and info.principal == "agent-y"


def test_revoked_token_rejected(pool):
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO tokens (token_hash, principal, scopes, revoked) "
            "VALUES (%s, %s, %s, true)",
            (hash_token("tok-revoked"), "agent-z", ["a"]),
        )
        conn.commit()
    assert lookup_token(pool, "tok-revoked") is None


def test_check_scope():
    assert check_scope("a", ["a"]) is True
    assert check_scope("b", ["a"]) is False
    assert check_scope("anything", ["*"]) is True


def test_allowed_projects_filters_to_scope():
    assert allowed_projects(["a"], ["a", "b"]) == ["a"]
    assert set(allowed_projects(["*"], ["a", "b"])) == {"a", "b"}


def test_audit_writes_row(pool):
    audit(pool, "agent-a", "query_graph", "a", "q=foo")
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT principal, tool, project_slug FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row == ("agent-a", "query_graph", "a")
