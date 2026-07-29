import os
from pathlib import Path

import pytest

from ckcommon.db import apply_migrations
from ckmcp import auth
from ckmcp.graphstore import GraphStore
from ckmcp.tools import MAX_NODES_HARD, ScopeError, Tools

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "db" / "migrations"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


class DictRegistry:
    def __init__(self, stores: dict[str, GraphStore]):
        self._s = stores

    def has(self, slug):
        return slug in self._s

    def get(self, slug):
        return self._s[slug]

    def list_slugs(self):
        return list(self._s)


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
            conn.execute(
                "INSERT INTO builds (project_slug, version_ts, status, node_count, edge_count, finished_at) "
                "VALUES (%s, %s, 'succeeded', 9, 18, now())",
                (slug, "20260728T000000"),
            )
        conn.commit()
    yield p
    p.close()


@pytest.fixture
def tools(pool):
    store = GraphStore.from_dir(FIXTURE)
    reg = DictRegistry({"a": store, "b": store})
    return Tools(reg, pool)


TOK_A = auth.TokenInfo(principal="agent-a", scopes=["a"])
TOK_ALL = auth.TokenInfo(principal="agent-super", scopes=["*"])


def test_list_projects_filtered_by_scope(tools):
    got = tools.list_projects(TOK_A)
    slugs = {p["slug"] for p in got}
    assert slugs == {"a"}
    assert got[0]["node_count"] == 9


def test_list_projects_wildcard_sees_all(tools):
    slugs = {p["slug"] for p in tools.list_projects(TOK_ALL)}
    assert slugs == {"a", "b"}


def test_scope_denied_raises(tools):
    with pytest.raises(ScopeError):
        tools.get_node(TOK_A, "b", "svc_db_conn")


def test_query_graph_caps_nodes(tools):
    res = tools.query_graph(TOK_A, "a", "svc", max_nodes=999)
    assert len(res["nodes"]) <= MAX_NODES_HARD


def test_query_graph_returns_summary(tools):
    res = tools.query_graph(TOK_A, "a", "conn")
    assert res["nodes"]
    assert isinstance(res["summary"], str)


def test_get_node(tools):
    d = tools.get_node(TOK_A, "a", "svc_db_conn")
    assert d["label"] == "conn()"


def test_trace_path(tools):
    res = tools.trace_path(TOK_A, "a", "svc_api_handle", "svc_db_conn")
    assert res["paths"]


def test_blast_radius(tools):
    res = tools.blast_radius(TOK_A, "a", "svc_db_conn", depth=2)
    ids = {n["id"] for n in res["impacted"]}
    assert {"svc_db_save", "svc_auth_verify"} <= ids


def test_search_cross_project_intersects_scope(tools):
    # TOK_A scoped to 'a' only -> cross-project search must not leak 'b'
    res = tools.search(TOK_A, "conn", project=None)
    assert {h["project"] for h in res["hits"]} <= {"a"}


def test_search_wildcard_spans_projects(tools):
    res = tools.search(TOK_ALL, "conn", project=None)
    assert {h["project"] for h in res["hits"]} == {"a", "b"}


def test_audit_written(tools, pool):
    tools.get_node(TOK_A, "a", "svc_db_conn")
    with pool.connection() as conn:
        n = conn.execute("SELECT count(*) FROM audit_log WHERE tool='get_node'").fetchone()
    assert n[0] >= 1


# --- SP1 Task 3: add_annotation tool --------------------------------------


def test_add_annotation_writes_and_scopes(tools, pool):
    res = tools.add_annotation(TOK_A, "a", "svc_db_conn", "explain this")
    assert isinstance(res["id"], int)
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT project_slug, node_id, content, principal FROM annotations "
            "WHERE id=%s",
            (res["id"],),
        ).fetchone()
    assert row == ("a", "svc_db_conn", "explain this", "agent-a")


def test_add_annotation_denied_out_of_scope(tools):
    with pytest.raises(ScopeError):
        tools.add_annotation(TOK_A, "b", "svc_db_conn", "nope")


def test_add_annotation_unknown_node_raises(tools):
    with pytest.raises(KeyError):
        tools.add_annotation(TOK_A, "a", "ghost", "nope")


def test_add_annotation_audited(tools, pool):
    tools.add_annotation(TOK_A, "a", "svc_db_conn", "note")
    with pool.connection() as conn:
        n = conn.execute(
            "SELECT count(*) FROM audit_log WHERE tool='add_annotation'"
        ).fetchone()[0]
    assert n >= 1


# --- SP1 Task 4: overlay + persistence across rebuild ---------------------


def test_get_node_overlays_annotations(tools):
    tools.add_annotation(TOK_A, "a", "svc_db_conn", "singleton on purpose")
    detail = tools.get_node(TOK_A, "a", "svc_db_conn")
    assert "annotations" in detail
    assert detail["annotations"][0]["content"] == "singleton on purpose"
    assert detail["annotations"][0]["tag"] == "CONTRIBUTED"


def test_get_node_without_annotations_is_empty_list(tools):
    detail = tools.get_node(TOK_A, "a", "svc_api_handle")
    assert detail["annotations"] == []


def test_query_graph_includes_annotation_count(tools):
    tools.add_annotation(TOK_A, "a", "svc_db_conn", "note")
    res = tools.query_graph(TOK_A, "a", "conn")
    conn_node = next(n for n in res["nodes"] if n["id"] == "svc_db_conn")
    assert conn_node["annotation_count"] >= 1


def test_annotation_survives_graph_rebuild(tools, pool):
    tools.add_annotation(TOK_A, "a", "svc_db_conn", "still here after rebuild")
    # simulate a rebuild: fresh Tools + freshly loaded store for the same project
    rebuilt_store = GraphStore.from_dir(FIXTURE)
    rebuilt = Tools(DictRegistry({"a": rebuilt_store, "b": rebuilt_store}), pool)
    detail = rebuilt.get_node(TOK_A, "a", "svc_db_conn")
    assert any(
        x["content"] == "still here after rebuild" for x in detail["annotations"]
    )
