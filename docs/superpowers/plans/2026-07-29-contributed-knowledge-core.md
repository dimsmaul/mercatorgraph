# Contributed-Knowledge Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist human/agent annotations in Postgres, expose an `add_annotation` MCP tool, and overlay those annotations (tagged `CONTRIBUTED`) into query results — so contributed knowledge survives graph rebuilds (PRD G3, §6, Fase 3 core).

**Architecture:** Annotations live in the existing Postgres `annotations` table, keyed by `(project_slug, node_id)`. Graph rebuilds only replace `graph.json` on the volume, so annotations are untouched and survive. The MCP tools layer reads annotations at query time and merges them into `get_node` / `query_graph` results — nothing is ever written into `graph.json` (derived-vs-contributed separation).

**Tech Stack:** Python 3.12, psycopg3 (plain SQL, no ORM), FastMCP, NetworkX, pytest.

## Global Constraints

- Python `>=3.12`; manage with `uv`; run tests with `uv run --python 3.12 pytest`.
- Postgres via psycopg3 + plain SQL migration files in `db/migrations/*.sql`. No ORM, no Alembic.
- DB-dependent tests require `DATABASE_URL`; they must `skipif` when it is unset.
- `CONTRIBUTED` knowledge is NEVER written into `graph.json` — overlay at query time only.
- Every MCP tool checks project scope and writes an audit row; results stay size-capped.
- Annotation overlay cap: `ANNOTATION_LIMIT = 50` per node.
- Microcommits: one commit per task. No `Co-Authored-By` trailer on any commit.
- The `annotations` table already exists (from `db/migrations/001_init.sql`):
  `annotations(id, project_slug, node_id, content, principal, status default 'open', created_at)`.

---

## File Structure

- `db/migrations/002_annotations_index.sql` — index for annotation lookups (new).
- `mcp/src/ckmcp/annotations.py` — annotation repository: write + read functions (new).
- `mcp/src/ckmcp/graphstore.py` — add `has_node()` accessor (modify).
- `mcp/src/ckmcp/tools.py` — `add_annotation` tool + overlay in `get_node`/`query_graph` (modify).
- `mcp/src/ckmcp/server.py` — register the `add_annotation` FastMCP tool (modify).
- `mcp/tests/test_annotations.py` — repository tests (new).
- `mcp/tests/test_tools.py` — tool + overlay + persistence-across-rebuild tests (modify).

---

## Task 1: Annotations index migration

**Files:**
- Create: `db/migrations/002_annotations_index.sql`
- Test: `mcp/tests/test_annotations.py`

**Interfaces:**
- Produces: an index `annotations_project_node_idx` on `annotations(project_slug, node_id)`.
- Consumes: `ckcommon.db.apply_migrations(pool, migrations_dir)` (existing).

- [ ] **Step 1: Write the failing test**

```python
# mcp/tests/test_annotations.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_annotations.py::test_annotations_index_exists -v`
Expected: FAIL — index not present.

- [ ] **Step 3: Write the migration**

```sql
-- db/migrations/002_annotations_index.sql
CREATE INDEX IF NOT EXISTS annotations_project_node_idx
    ON annotations (project_slug, node_id);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_annotations.py::test_annotations_index_exists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add db/migrations/002_annotations_index.sql mcp/tests/test_annotations.py
git commit -m "feat(db): index annotations by project + node"
```

---

## Task 2: Annotations repository

**Files:**
- Create: `mcp/src/ckmcp/annotations.py`
- Test: `mcp/tests/test_annotations.py` (append)

**Interfaces:**
- Consumes: `psycopg_pool.ConnectionPool`; `ckcommon.schema.Confidence.CONTRIBUTED`.
- Produces:
  - `add_annotation(pool, project: str, node_id: str, content: str, principal: str) -> int`
  - `annotations_for_nodes(pool, project: str, node_ids: list[str]) -> dict[str, list[dict]]`
    where each dict is `{id, content, principal, status, created_at, tag}` and `tag == "CONTRIBUTED"`.
  - `annotation_counts(pool, project: str, node_ids: list[str]) -> dict[str, int]`
  - Module constant `ANNOTATION_LIMIT = 50`.

- [ ] **Step 1: Write the failing tests**

```python
# append to mcp/tests/test_annotations.py
from ckmcp.annotations import (
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_annotations.py -v`
Expected: FAIL — `ModuleNotFoundError: ckmcp.annotations`.

- [ ] **Step 3: Write the repository**

```python
# mcp/src/ckmcp/annotations.py
"""Contributed-knowledge store (Postgres).

Annotations persist independently of the graph: a rebuild replaces graph.json on the
volume but never touches this table, so contributed knowledge survives (PRD G3). Read
functions tag each annotation CONTRIBUTED for overlay into query results.
"""

from __future__ import annotations

from psycopg_pool import ConnectionPool

from ckcommon.schema import Confidence

ANNOTATION_LIMIT = 50


def add_annotation(
    pool: ConnectionPool, project: str, node_id: str, content: str, principal: str
) -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO annotations (project_slug, node_id, content, principal) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (project, node_id, content, principal),
        ).fetchone()
        conn.commit()
    return row[0]


def annotations_for_nodes(
    pool: ConnectionPool, project: str, node_ids: list[str]
) -> dict[str, list[dict]]:
    if not node_ids:
        return {}
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, node_id, content, principal, status, created_at "
            "FROM annotations WHERE project_slug = %s AND node_id = ANY(%s) "
            "ORDER BY created_at",
            (project, list(node_ids)),
        ).fetchall()
    out: dict[str, list[dict]] = {}
    for id_, node_id, content, principal, status, created in rows:
        bucket = out.setdefault(node_id, [])
        if len(bucket) >= ANNOTATION_LIMIT:
            continue
        bucket.append(
            {
                "id": id_,
                "content": content,
                "principal": principal,
                "status": status,
                "created_at": created.isoformat() if created else None,
                "tag": Confidence.CONTRIBUTED.value,
            }
        )
    return out


def annotation_counts(
    pool: ConnectionPool, project: str, node_ids: list[str]
) -> dict[str, int]:
    if not node_ids:
        return {}
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT node_id, count(*) FROM annotations "
            "WHERE project_slug = %s AND node_id = ANY(%s) GROUP BY node_id",
            (project, list(node_ids)),
        ).fetchall()
    return {node_id: count for node_id, count in rows}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_annotations.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add mcp/src/ckmcp/annotations.py mcp/tests/test_annotations.py
git commit -m "feat(mcp): annotations repository (persist + read, CONTRIBUTED tag)"
```

---

## Task 3: `add_annotation` MCP tool

**Files:**
- Modify: `mcp/src/ckmcp/graphstore.py` (add `has_node`)
- Modify: `mcp/src/ckmcp/tools.py` (add `add_annotation` method)
- Modify: `mcp/src/ckmcp/server.py` (register tool)
- Test: `mcp/tests/test_tools.py` (append)

**Interfaces:**
- Consumes: `ckmcp.annotations.add_annotation`; `auth.check_scope`, `auth.audit`;
  `GraphStore.has_node(node_id) -> bool`.
- Produces: `Tools.add_annotation(token: auth.TokenInfo, project: str, node_id: str, content: str) -> dict`
  returning `{"id": int}`; raises `ScopeError` when out of scope, `KeyError` for unknown node.

- [ ] **Step 1: Write the failing tests**

```python
# append to mcp/tests/test_tools.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_tools.py -k add_annotation -v`
Expected: FAIL — `Tools` has no `add_annotation`.

- [ ] **Step 3a: Add `has_node` to GraphStore**

In `mcp/src/ckmcp/graphstore.py`, add this method to the `GraphStore` class (next to `node_detail`):

```python
    def has_node(self, node_id: str) -> bool:
        return node_id in self._g
```

- [ ] **Step 3b: Add the `add_annotation` method to `Tools`**

In `mcp/src/ckmcp/tools.py`, add the import near the top:

```python
from ckmcp import annotations
```

Then add this method to the `Tools` class (after `get_node`):

```python
    def add_annotation(
        self, token: auth.TokenInfo, project: str, node_id: str, content: str
    ) -> dict:
        self._require_scope(token, project)
        store = self._store(project)
        if not store.has_node(node_id):
            raise KeyError(f"node {node_id!r} not in project {project!r}")
        annotation_id = annotations.add_annotation(
            self._pool, project, node_id, content, token.principal
        )
        auth.audit(self._pool, token.principal, "add_annotation", project, node_id)
        return {"id": annotation_id}
```

- [ ] **Step 3c: Register the tool in the server**

In `mcp/src/ckmcp/server.py`, add inside `build_server` (after the `get_node` tool):

```python
    @mcp.tool
    async def add_annotation(project: str, node_id: str, content: str) -> dict:
        """Attach a persistent note to a node (contributed knowledge)."""
        tok = current_token()
        return await anyio.to_thread.run_sync(
            tools.add_annotation, tok, project, node_id, content
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_tools.py -k add_annotation -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git add mcp/src/ckmcp/graphstore.py mcp/src/ckmcp/tools.py mcp/src/ckmcp/server.py mcp/tests/test_tools.py
git commit -m "feat(mcp): add_annotation tool (scoped, audited, node-checked)"
```

---

## Task 4: Overlay annotations into query results + prove persistence

**Files:**
- Modify: `mcp/src/ckmcp/tools.py` (`get_node`, `query_graph`)
- Test: `mcp/tests/test_tools.py` (append)

**Interfaces:**
- Consumes: `annotations.annotations_for_nodes`, `annotations.annotation_counts`.
- Produces: `get_node(...)` result gains `"annotations": list[dict]`;
  `query_graph(...)` node dicts gain `"annotation_count": int`.

- [ ] **Step 1: Write the failing tests**

```python
# append to mcp/tests/test_tools.py
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
    # add contributed knowledge
    tools.add_annotation(TOK_A, "a", "svc_db_conn", "still here after rebuild")
    # simulate a rebuild: a brand-new Tools with a freshly loaded store for the same project
    from ckmcp.graphstore import GraphStore
    from ckmcp.tools import Tools

    rebuilt_store = GraphStore.from_dir(FIXTURE)
    rebuilt = Tools(DictRegistry({"a": rebuilt_store, "b": rebuilt_store}), pool)
    detail = rebuilt.get_node(TOK_A, "a", "svc_db_conn")
    assert any(x["content"] == "still here after rebuild" for x in detail["annotations"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_tools.py -k "annotation or overlay or rebuild" -v`
Expected: FAIL — `get_node` result has no `annotations` key.

- [ ] **Step 3: Overlay in `get_node` and `query_graph`**

In `mcp/src/ckmcp/tools.py`, change `get_node` — after `detail = store.node_detail(node_id)` and before the audit line, add:

```python
        detail["annotations"] = annotations.annotations_for_nodes(
            self._pool, project, [node_id]
        ).get(node_id, [])
```

In `query_graph`, after computing `sub = store.neighborhood(...)` and before building the summary, add:

```python
        counts = annotations.annotation_counts(
            self._pool, project, [n["id"] for n in sub["nodes"]]
        )
        for node in sub["nodes"]:
            node["annotation_count"] = counts.get(node["id"], 0)
```

(The empty-seed early return in `query_graph` returns `{"nodes": [], ...}` — no nodes to annotate, leave it unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_tools.py -k "annotation or overlay or rebuild" -v`
Expected: PASS (all four, including `test_annotation_survives_graph_rebuild` — G3).

- [ ] **Step 5: Run the full suite**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest -q`
Expected: all pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add mcp/src/ckmcp/tools.py mcp/tests/test_tools.py
git commit -m "feat(mcp): overlay CONTRIBUTED annotations in get_node + query_graph"
```

---

## Self-Review

**Spec coverage:**
- G3 knowledge persists across rebuild → Task 4 `test_annotation_survives_graph_rebuild`.
- §6 `add_annotation` tool → Task 3.
- `CONTRIBUTED` tag in query results → Task 2 (tag) + Task 4 (overlay).
- Persistence store / not in graph.json → Task 2 (Postgres repo), overlay-only in Task 4.

**Placeholder scan:** none — every step has concrete code.

**Type consistency:** `add_annotation(pool, project, node_id, content, principal) -> int`
used identically in repo (Task 2) and tool (Task 3). `annotations_for_nodes` /
`annotation_counts` signatures match between Task 2 and Task 4. `has_node` defined in
Task 3a, used in Task 3b.

## Deferred (later sub-projects)

- Annotation approval before it appears to other agents (PRD open-Q3) — not gated here; any
  scoped principal may add. Approval workflow is SP2/SP3.
- Thread status transitions (`addressed-by-agent` / `resolved`) — SP2 (docs comments).
- Comment → agent → PR + diff/approval — SP3.
