# Graph Diff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let an agent query what changed between two versions of a project's graph — nodes/edges added and removed (PRD Fase 4, "query perubahan graph antar dua release/commit").

**Architecture:** Graph versions already persist on the volume at
`data/projects/<slug>/versions/<ts>/graphify-out/graph.json`. A pure `diff_graphs(old, new)`
compares two node-link dicts. The MCP registry gains version-listing + version-loading; a new
scoped `graph_diff` MCP tool defaults to the two most recent versions and returns a size-capped
summary.

**Tech Stack:** Python 3.12, NetworkX-format node-link JSON, FastMCP, pytest.

## Global Constraints

- Python `>=3.12`; `uv run --python 3.12 pytest`.
- Reuse `ckcommon.schema.parse_graph` for node/edge parsing; never hand-parse elsewhere.
- Every MCP tool checks scope, audits, and caps results. Diff cap: `DIFF_LIMIT = 100` per list.
- DB tests `skipif` without `DATABASE_URL`. Microcommits, no `Co-Authored-By` trailer.
- Version dir layout is owned by `promote.py`: `versions/<ts>/graphify-out/graph.json`.

## File Structure

- `mcp/src/ckmcp/graphdiff.py` — pure `diff_graphs(old, new)` (new).
- `mcp/src/ckmcp/registry.py` — `list_versions`, `load_version_json` (modify).
- `mcp/src/ckmcp/tools.py` — `graph_diff` tool + `DIFF_LIMIT` (modify).
- `mcp/src/ckmcp/server.py` — register `graph_diff` (modify).
- `mcp/tests/test_graphdiff.py` — pure-function tests (new).
- `mcp/tests/test_registry_versions.py` — version access tests (new).
- `mcp/tests/test_tools.py` — `graph_diff` tool tests (modify).

---

## Task 1: Pure `diff_graphs`

**Files:**
- Create: `mcp/src/ckmcp/graphdiff.py`
- Test: `mcp/tests/test_graphdiff.py`

**Interfaces:**
- Consumes: `ckcommon.schema.parse_graph(data) -> (nodes, edges)`.
- Produces: `diff_graphs(old: dict, new: dict) -> dict` with keys
  `nodes_added`, `nodes_removed` (each `list[{id,label}]`),
  `edges_added`, `edges_removed` (each `list[{source,target,relation}]`),
  `counts` (`{nodes_added,nodes_removed,edges_added,edges_removed}`).

- [ ] **Step 1: Write the failing test**

```python
# mcp/tests/test_graphdiff.py
import json
from pathlib import Path

from ckmcp.graphdiff import diff_graphs

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out" / "graph.json"


def _load():
    return json.loads(FIXTURE.read_text())


def test_no_change_is_empty():
    g = _load()
    d = diff_graphs(g, g)
    assert d["counts"] == {
        "nodes_added": 0,
        "nodes_removed": 0,
        "edges_added": 0,
        "edges_removed": 0,
    }


def test_detects_added_and_removed():
    old = _load()
    new = json.loads(json.dumps(old))  # deep copy
    # remove a node + its edges from `old` perspective: drop svc_db_conn from new
    new["nodes"] = [n for n in new["nodes"] if n["id"] != "svc_db_conn"]
    new["links"] = [
        e for e in new["links"]
        if e["source"] != "svc_db_conn" and e["target"] != "svc_db_conn"
    ]
    d = diff_graphs(old, new)
    removed_ids = {n["id"] for n in d["nodes_removed"]}
    assert "svc_db_conn" in removed_ids
    assert d["counts"]["edges_removed"] > 0
    # symmetry: adding is the reverse
    d2 = diff_graphs(new, old)
    added_ids = {n["id"] for n in d2["nodes_added"]}
    assert "svc_db_conn" in added_ids


def test_edge_identity_by_source_target_relation():
    old = _load()
    new = json.loads(json.dumps(old))
    new["links"][0]["relation"] = "CHANGED_REL"
    d = diff_graphs(old, new)
    assert d["counts"]["edges_added"] == 1
    assert d["counts"]["edges_removed"] == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --python 3.12 pytest mcp/tests/test_graphdiff.py -v`
Expected: FAIL — `ModuleNotFoundError: ckmcp.graphdiff`.

- [ ] **Step 3: Implement**

```python
# mcp/src/ckmcp/graphdiff.py
"""Pure diff between two graphify node-link graphs (added/removed nodes and edges)."""

from __future__ import annotations

from ckcommon.schema import parse_graph


def _edge_key(e) -> tuple:
    return (e.source, e.target, e.relation)


def diff_graphs(old: dict, new: dict) -> dict:
    old_nodes, old_edges = parse_graph(old)
    new_nodes, new_edges = parse_graph(new)

    old_n = {n.id: n for n in old_nodes}
    new_n = {n.id: n for n in new_nodes}
    nodes_added = [
        {"id": nid, "label": new_n[nid].label} for nid in new_n.keys() - old_n.keys()
    ]
    nodes_removed = [
        {"id": nid, "label": old_n[nid].label} for nid in old_n.keys() - new_n.keys()
    ]

    old_e = {_edge_key(e): e for e in old_edges}
    new_e = {_edge_key(e): e for e in new_edges}

    def _edge_view(e) -> dict:
        return {"source": e.source, "target": e.target, "relation": e.relation}

    edges_added = [_edge_view(new_e[k]) for k in new_e.keys() - old_e.keys()]
    edges_removed = [_edge_view(old_e[k]) for k in old_e.keys() - new_e.keys()]

    return {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "edges_added": edges_added,
        "edges_removed": edges_removed,
        "counts": {
            "nodes_added": len(nodes_added),
            "nodes_removed": len(nodes_removed),
            "edges_added": len(edges_added),
            "edges_removed": len(edges_removed),
        },
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 pytest mcp/tests/test_graphdiff.py -v`  → PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp/src/ckmcp/graphdiff.py mcp/tests/test_graphdiff.py
git commit -m "feat(mcp): pure graph diff (added/removed nodes and edges)"
```

---

## Task 2: Version access on the registry

**Files:**
- Modify: `mcp/src/ckmcp/registry.py`
- Test: `mcp/tests/test_registry_versions.py`

**Interfaces:**
- Consumes: `ckcommon.schema.GRAPHIFY_OUT_DIR`, `GRAPH_JSON`.
- Produces on `FsGraphRegistry`:
  - `list_versions(slug: str) -> list[str]` — version timestamps, oldest→newest.
  - `load_version_json(slug: str, version: str) -> dict` — raw graph.json for that version.

- [ ] **Step 1: Write the failing test**

```python
# mcp/tests/test_registry_versions.py
import json
from pathlib import Path

import pytest

from ckcommon.schema import GRAPHIFY_OUT_DIR
from ckmcp.registry import FsGraphRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out" / "graph.json"


def _make_version(root: Path, slug: str, version: str, graph: dict) -> None:
    out = root / "projects" / slug / "versions" / version / GRAPHIFY_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps(graph))


def test_list_versions_sorted(tmp_path):
    g = json.loads(FIXTURE.read_text())
    _make_version(tmp_path, "demo", "20260101T000000", g)
    _make_version(tmp_path, "demo", "20260102T000000", g)
    reg = FsGraphRegistry(tmp_path)
    assert reg.list_versions("demo") == ["20260101T000000", "20260102T000000"]


def test_load_version_json(tmp_path):
    g = json.loads(FIXTURE.read_text())
    _make_version(tmp_path, "demo", "20260101T000000", g)
    reg = FsGraphRegistry(tmp_path)
    loaded = reg.load_version_json("demo", "20260101T000000")
    assert len(loaded["nodes"]) == len(g["nodes"])


def test_list_versions_missing_project_is_empty(tmp_path):
    assert FsGraphRegistry(tmp_path).list_versions("nope") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --python 3.12 pytest mcp/tests/test_registry_versions.py -v`
Expected: FAIL — `FsGraphRegistry` has no `list_versions`.

- [ ] **Step 3: Implement** — add to `FsGraphRegistry` in `mcp/src/ckmcp/registry.py`:

```python
    def _versions_dir(self, slug: str):
        return self._root / slug / "versions"

    def list_versions(self, slug: str) -> list[str]:
        vdir = self._versions_dir(slug)
        if not vdir.exists():
            return []
        return sorted(p.name for p in vdir.iterdir() if p.is_dir())

    def load_version_json(self, slug: str, version: str) -> dict:
        import json

        path = self._versions_dir(slug) / version / GRAPHIFY_OUT_DIR / GRAPH_JSON
        if not path.exists():
            raise KeyError(f"version {version!r} of {slug!r} not found")
        return json.loads(path.read_text())
```

Add `GRAPH_JSON` to the existing schema import at the top of the file:
`from ckcommon.schema import GRAPH_JSON, GRAPHIFY_OUT_DIR`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run --python 3.12 pytest mcp/tests/test_registry_versions.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp/src/ckmcp/registry.py mcp/tests/test_registry_versions.py
git commit -m "feat(mcp): registry version listing + loading"
```

---

## Task 3: `graph_diff` tool

**Files:**
- Modify: `mcp/src/ckmcp/tools.py`
- Test: `mcp/tests/test_tools.py` (append)

**Interfaces:**
- Consumes: `graphdiff.diff_graphs`; registry `list_versions` / `load_version_json`;
  `auth.check_scope`, `auth.audit`.
- Produces: `Tools.graph_diff(token, project, from_version=None, to_version=None) -> dict`.
  Defaults: `to_version` = newest, `from_version` = second-newest. Each list capped at
  `DIFF_LIMIT`; `counts` are always exact. Raises `ScopeError` out of scope; `ValueError`
  when fewer than two versions and none specified.
- Extends the `GraphRegistry` Protocol with `list_versions` + `load_version_json`; the test
  `DictRegistry` gains a `versions` mapping.

- [ ] **Step 1: Write the failing tests** (append to `mcp/tests/test_tools.py`)

First extend `DictRegistry` (top of file) to hold versions:

```python
# in DictRegistry.__init__ add:  self._versions = versions or {}
# and methods:
    def list_versions(self, slug):
        return sorted((self._versions.get(slug) or {}).keys())

    def load_version_json(self, slug, version):
        return self._versions[slug][version]
```

Then the tests:

```python
def _mod_graph(graph, drop_id):
    import json as _json
    g = _json.loads(_json.dumps(graph))
    g["nodes"] = [n for n in g["nodes"] if n["id"] != drop_id]
    g["links"] = [
        e for e in g["links"] if e["source"] != drop_id and e["target"] != drop_id
    ]
    return g


@pytest.fixture
def diff_tools(pool):
    import json
    store = GraphStore.from_dir(FIXTURE)
    g = json.loads((FIXTURE / "graph.json").read_text())
    versions = {"a": {"v1": g, "v2": _mod_graph(g, "svc_db_conn")}}
    reg = DictRegistry({"a": store, "b": store}, versions=versions)
    return Tools(reg, pool)


def test_graph_diff_default_last_two(diff_tools):
    res = diff_tools.graph_diff(TOK_A, "a")
    removed = {n["id"] for n in res["nodes_removed"]}
    assert "svc_db_conn" in removed
    assert res["from_version"] == "v1"
    assert res["to_version"] == "v2"


def test_graph_diff_scope_denied(diff_tools):
    with pytest.raises(ScopeError):
        diff_tools.graph_diff(TOK_A, "b")


def test_graph_diff_needs_two_versions(pool):
    import json
    store = GraphStore.from_dir(FIXTURE)
    g = json.loads((FIXTURE / "graph.json").read_text())
    reg = DictRegistry({"a": store}, versions={"a": {"only": g}})
    t = Tools(reg, pool)
    with pytest.raises(ValueError):
        t.graph_diff(TOK_A, "a")
```

(Update the `DictRegistry(...)` constructor calls in existing fixtures to accept the new
optional `versions=None` kwarg — add `versions=None` to `__init__`.)

- [ ] **Step 2: Run to verify it fails**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_tools.py -k graph_diff -v`
Expected: FAIL — `Tools` has no `graph_diff`.

- [ ] **Step 3: Implement** — in `mcp/src/ckmcp/tools.py`:

Add import: `from ckmcp import annotations, auth, graphdiff` (extend existing line) and constant
near the other caps: `DIFF_LIMIT = 100`. Extend the `GraphRegistry` Protocol:

```python
    def list_versions(self, slug: str) -> list[str]: ...
    def load_version_json(self, slug: str, version: str) -> dict: ...
```

Add the method to `Tools`:

```python
    def graph_diff(
        self,
        token: auth.TokenInfo,
        project: str,
        from_version: str | None = None,
        to_version: str | None = None,
    ) -> dict:
        self._require_scope(token, project)
        versions = self._reg.list_versions(project)
        if to_version is None or from_version is None:
            if len(versions) < 2:
                raise ValueError("need at least two versions to diff")
            to_version = to_version or versions[-1]
            from_version = from_version or versions[-2]
        old = self._reg.load_version_json(project, from_version)
        new = self._reg.load_version_json(project, to_version)
        diff = graphdiff.diff_graphs(old, new)
        for key in ("nodes_added", "nodes_removed", "edges_added", "edges_removed"):
            diff[key] = diff[key][:DIFF_LIMIT]
        diff["from_version"] = from_version
        diff["to_version"] = to_version
        auth.audit(
            self._pool, token.principal, "graph_diff", project, f"{from_version}->{to_version}"
        )
        return diff
```

- [ ] **Step 4: Run to verify pass**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest mcp/tests/test_tools.py -k graph_diff -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp/src/ckmcp/tools.py mcp/tests/test_tools.py
git commit -m "feat(mcp): graph_diff tool (default last two versions, scoped, capped)"
```

---

## Task 4: Register tool + full suite

**Files:**
- Modify: `mcp/src/ckmcp/server.py`

- [ ] **Step 1: Register** — in `build_server`, after `blast_radius`:

```python
    @mcp.tool
    async def graph_diff(
        project: str, from_version: str | None = None, to_version: str | None = None
    ) -> dict:
        """What changed between two graph versions (defaults to the last two)."""
        tok = current_token()
        return await anyio.to_thread.run_sync(
            tools.graph_diff, tok, project, from_version, to_version
        )
```

- [ ] **Step 2: Run the full suite**

Run: `DATABASE_URL=$DB uv run --python 3.12 pytest -q` → all pass.

- [ ] **Step 3: Commit**

```bash
git add mcp/src/ckmcp/server.py
git commit -m "feat(mcp): register graph_diff MCP tool"
```

---

## Self-Review

**Spec coverage:** Fase 4 "graph diff between two versions" → Tasks 1–4. Agent-facing via MCP.
**Placeholder scan:** none — all steps have concrete code.
**Type consistency:** `diff_graphs(old,new)->dict` (Task 1) used in Task 3; `list_versions` /
`load_version_json` defined in Task 2, declared in the Protocol + implemented by `DictRegistry`
in Task 3, called in Task 3's `Tools.graph_diff`; `graph_diff` signature identical in Tools
(Task 3) and server (Task 4).

## Deferred
- Diff by git commit (not just build version) — needs commit→version mapping; later.
- Rendering the diff in the docs UI — separate (docs pipeline A).
