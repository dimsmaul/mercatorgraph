"""The 6 Fase 1 MCP tools.

Every tool: (1) checks project scope, (2) runs against the in-process graph store,
(3) enforces a hard size cap server-side, (4) writes an audit row. No tool ever returns the
whole graph. Tools are transport-agnostic here; ``server.py`` wires them into FastMCP.
"""

from __future__ import annotations

from typing import Protocol

from psycopg_pool import ConnectionPool

from ckmcp import annotations, auth
from ckmcp.graphstore import GraphStore

# hard caps — enforced regardless of caller input
MAX_NODES_DEFAULT = 30
MAX_NODES_HARD = 100
SEARCH_LIMIT_DEFAULT = 20
SEARCH_LIMIT_HARD = 50
DEPTH_DEFAULT = 2
DEPTH_HARD = 4
SUMMARY_TOP = 5


class ScopeError(PermissionError):
    """Raised when a principal queries a project outside its scope."""


class GraphRegistry(Protocol):
    def has(self, slug: str) -> bool: ...
    def get(self, slug: str) -> GraphStore: ...
    def list_slugs(self) -> list[str]: ...


def _clamp(value: int | None, default: int, hard: int) -> int:
    if value is None:
        return default
    return max(1, min(value, hard))


class Tools:
    def __init__(self, registry: GraphRegistry, pool: ConnectionPool) -> None:
        self._reg = registry
        self._pool = pool

    # --- scope helpers ----------------------------------------------------

    def _require_scope(self, token: auth.TokenInfo, project: str) -> None:
        if not auth.check_scope(project, token.scopes):
            raise ScopeError(f"{token.principal} not scoped for project {project!r}")

    def _store(self, project: str) -> GraphStore:
        if not self._reg.has(project):
            raise KeyError(f"project {project!r} not indexed")
        return self._reg.get(project)

    # --- tools ------------------------------------------------------------

    def list_projects(self, token: auth.TokenInfo) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT p.slug, b.version_ts, b.node_count, b.edge_count, b.finished_at
                FROM projects p
                LEFT JOIN LATERAL (
                    SELECT version_ts, node_count, edge_count, finished_at
                    FROM builds
                    WHERE project_slug = p.slug AND status = 'succeeded'
                    ORDER BY started_at DESC LIMIT 1
                ) b ON true
                ORDER BY p.slug
                """
            ).fetchall()
        out = []
        for slug, version_ts, nc, ec, finished in rows:
            if not auth.check_scope(slug, token.scopes):
                continue
            out.append(
                {
                    "slug": slug,
                    "last_build": version_ts,
                    "last_build_at": finished.isoformat() if finished else None,
                    "node_count": nc,
                    "edge_count": ec,
                }
            )
        auth.audit(self._pool, token.principal, "list_projects", None)
        return out

    def query_graph(
        self,
        token: auth.TokenInfo,
        project: str,
        question: str,
        max_nodes: int | None = None,
    ) -> dict:
        self._require_scope(token, project)
        store = self._store(project)
        cap = _clamp(max_nodes, MAX_NODES_DEFAULT, MAX_NODES_HARD)

        seeds = [h["ref"] for h in store.search(question, limit=cap) if h["kind"] == "node"]
        if not seeds:
            auth.audit(self._pool, token.principal, "query_graph", project, question)
            return {"nodes": [], "edges": [], "summary": "No matching nodes."}

        sub = store.neighborhood(seeds, max_nodes=cap)
        counts = annotations.annotation_counts(
            self._pool, project, [n["id"] for n in sub["nodes"]]
        )
        for node in sub["nodes"]:
            node["annotation_count"] = counts.get(node["id"], 0)
        bc = store.betweenness()
        top = sorted(sub["nodes"], key=lambda n: bc.get(n["id"], 0.0), reverse=True)[
            :SUMMARY_TOP
        ]
        summary = "; ".join(
            f"{n['label']} ({n['source_file']})" for n in top if n.get("label")
        )
        auth.audit(self._pool, token.principal, "query_graph", project, question)
        return {"nodes": sub["nodes"], "edges": sub["edges"], "summary": summary}

    def get_node(self, token: auth.TokenInfo, project: str, node_id: str) -> dict:
        self._require_scope(token, project)
        store = self._store(project)
        detail = store.node_detail(node_id)
        detail["annotations"] = annotations.annotations_for_nodes(
            self._pool, project, [node_id]
        ).get(node_id, [])
        auth.audit(self._pool, token.principal, "get_node", project, node_id)
        return detail

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

    def trace_path(
        self,
        token: auth.TokenInfo,
        project: str,
        from_node: str,
        to_node: str,
        max_paths: int | None = None,
    ) -> dict:
        self._require_scope(token, project)
        store = self._store(project)
        cap = _clamp(max_paths, 1, 5)
        paths = store.paths(from_node, to_node, max_paths=cap)
        auth.audit(
            self._pool, token.principal, "trace_path", project, f"{from_node}->{to_node}"
        )
        return {"from": from_node, "to": to_node, "paths": paths}

    def blast_radius(
        self,
        token: auth.TokenInfo,
        project: str,
        node_id: str,
        depth: int | None = None,
    ) -> dict:
        self._require_scope(token, project)
        store = self._store(project)
        d = _clamp(depth, DEPTH_DEFAULT, DEPTH_HARD)
        impacted = store.blast_radius(node_id, depth=d)[:MAX_NODES_HARD]
        auth.audit(self._pool, token.principal, "blast_radius", project, node_id)
        return {"node_id": node_id, "depth": d, "impacted": impacted}

    def search(
        self,
        token: auth.TokenInfo,
        query: str,
        project: str | None = None,
        limit: int | None = None,
    ) -> dict:
        cap = _clamp(limit, SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_HARD)
        if project is not None:
            self._require_scope(token, project)
            targets = [project]
        else:
            targets = auth.allowed_projects(token.scopes, self._reg.list_slugs())

        hits: list[dict] = []
        for slug in targets:
            if not self._reg.has(slug):
                continue
            for h in self._reg.get(slug).search(query, limit=cap):
                hits.append({**h, "project": slug})
        hits = hits[:cap]
        auth.audit(self._pool, token.principal, "search", project, query)
        return {"query": query, "hits": hits}
