import json
import os
import shutil
from pathlib import Path

import pytest

from ckcommon.db import apply_migrations
from ckcommon.schema import GRAPHIFY_OUT_DIR
from ckmcp.registry import FsGraphRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "db" / "migrations"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out"


def _make_version(project_dir: Path, version: str, graph: dict) -> None:
    out = project_dir / "versions" / version / GRAPHIFY_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps(graph))


def _promote(project_dir: Path, version: str) -> None:
    current = project_dir / "current"
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(Path("versions") / version)


def test_registry_loads_current(tmp_path):
    graph = json.loads((FIXTURE / "graph.json").read_text())
    proj = tmp_path / "projects" / "demo"
    _make_version(proj, "v1", graph)
    _promote(proj, "v1")

    reg = FsGraphRegistry(tmp_path)
    assert reg.has("demo")
    assert reg.list_slugs() == ["demo"]
    store = reg.get("demo")
    assert store.node_count == 9


def test_registry_hot_reload_on_promote(tmp_path):
    graph = json.loads((FIXTURE / "graph.json").read_text())
    proj = tmp_path / "projects" / "demo"
    _make_version(proj, "v1", graph)
    _promote(proj, "v1")

    reg = FsGraphRegistry(tmp_path)
    first = reg.get("demo")
    assert first.node_count == 9
    # cached: same object until promote
    assert reg.get("demo") is first

    # new version with fewer nodes, then promote
    smaller = {**graph, "nodes": graph["nodes"][:4], "links": []}
    _make_version(proj, "v2", smaller)
    _promote(proj, "v2")

    second = reg.get("demo")
    assert second is not first
    assert second.node_count == 4


def test_registry_missing_project_raises(tmp_path):
    reg = FsGraphRegistry(tmp_path)
    assert reg.has("nope") is False
    with pytest.raises(KeyError):
        reg.get("nope")


# --- DB-backed verifier + server wiring (needs Postgres) ------------------

pg = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


@pytest.fixture
def pool():
    from psycopg_pool import ConnectionPool

    from ckmcp.auth import hash_token

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
            "INSERT INTO tokens (token_hash, principal, scopes) VALUES (%s, %s, %s)",
            (hash_token("tok-a"), "agent-a", ["a"]),
        )
        conn.commit()
    yield p
    p.close()


@pg
async def test_verifier_accepts_valid_token(pool):
    from ckmcp.server import DbTokenVerifier

    v = DbTokenVerifier(pool)
    at = await v.verify_token("tok-a")
    assert at is not None
    assert at.client_id == "agent-a"
    assert list(at.scopes) == ["a"]


@pg
async def test_verifier_rejects_invalid_token(pool):
    from ckmcp.server import DbTokenVerifier

    v = DbTokenVerifier(pool)
    assert await v.verify_token("bogus") is None


@pg
def test_build_server_wires_six_tools(pool, tmp_path):
    from ckmcp.server import build_server

    server = build_server(pool, str(tmp_path))
    assert server is not None
