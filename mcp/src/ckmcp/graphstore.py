"""In-process graph store over a graphify ``graph.json``.

Decision C: graphify owns *extraction*; we consume its node-link output with networkx and
do traversal in-process. No CLI text parsing. graphify writes ``directed: false``, but its
links carry real ``source -> target`` semantics (calls, contains, imports), so we load a
``DiGraph`` to preserve direction for path / blast-radius.

Full-text search uses an in-memory SQLite FTS5 index over node labels + source files +
community names + the GRAPH_REPORT.md text. This is a per-project read index, rebuilt on
each graph load.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import networkx as nx

from ckcommon.schema import (
    GRAPH_JSON,
    REPORT_MD,
    Confidence,
    parse_graph,
)


class GraphStore:
    def __init__(self, graph: nx.DiGraph, report_text: str = "") -> None:
        self._g = graph
        self._report_text = report_text
        self._betweenness: dict[str, float] | None = None
        self._fts = self._build_fts()

    # --- construction -----------------------------------------------------

    @classmethod
    def from_json(cls, data: dict, report_text: str = "") -> "GraphStore":
        nodes, edges = parse_graph(data)
        g: nx.DiGraph = nx.DiGraph()
        for n in nodes:
            g.add_node(
                n.id,
                label=n.label,
                file_type=n.file_type,
                source_file=n.source_file,
                source_location=n.source_location,
                community=n.community,
                community_name=n.community_name,
            )
        for e in edges:
            g.add_edge(
                e.source,
                e.target,
                relation=e.relation,
                confidence=e.confidence.value,
                confidence_score=e.confidence_score,
                explanation=e.explanation,
                source_location=e.source_location,
            )
        return cls(g, report_text)

    @classmethod
    def from_dir(cls, graphify_out_dir: str | Path) -> "GraphStore":
        d = Path(graphify_out_dir)
        data = json.loads((d / GRAPH_JSON).read_text())
        report_path = d / REPORT_MD
        report = report_path.read_text() if report_path.exists() else ""
        return cls.from_json(data, report)

    # --- basic accessors --------------------------------------------------

    @property
    def node_count(self) -> int:
        return self._g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def betweenness(self) -> dict[str, float]:
        """Betweenness centrality, computed once and cached."""
        if self._betweenness is None:
            self._betweenness = nx.betweenness_centrality(self._g)
        return self._betweenness

    # --- serialization helpers -------------------------------------------

    def _node_view(self, node_id: str) -> dict:
        attrs = self._g.nodes[node_id]
        return {
            "id": node_id,
            "label": attrs.get("label"),
            "file_type": attrs.get("file_type"),
            "source_file": attrs.get("source_file"),
            "source_location": attrs.get("source_location"),
            "community": attrs.get("community"),
            "community_name": attrs.get("community_name"),
            "degree": self._g.degree(node_id),
        }

    def _edge_view(self, u: str, v: str, direction: str) -> dict:
        a = self._g.edges[u, v]
        return {
            "source": u,
            "target": v,
            "direction": direction,
            "relation": a.get("relation"),
            "confidence": a.get("confidence", Confidence.INFERRED.value),
            "confidence_score": a.get("confidence_score"),
            "explanation": a.get("explanation"),
            "source_location": a.get("source_location"),
        }

    # --- queries ----------------------------------------------------------

    def has_node(self, node_id: str) -> bool:
        return node_id in self._g

    def node_detail(self, node_id: str) -> dict:
        if node_id not in self._g:
            raise KeyError(node_id)
        edges = [self._edge_view(node_id, v, "out") for v in self._g.successors(node_id)]
        edges += [self._edge_view(u, node_id, "in") for u in self._g.predecessors(node_id)]
        view = self._node_view(node_id)
        view["edges"] = edges
        return view

    def paths(self, source: str, target: str, max_paths: int = 1) -> list[dict]:
        if source not in self._g or target not in self._g:
            return []
        results: list[dict] = []
        try:
            for node_seq in nx.shortest_simple_paths(self._g, source, target):
                hops = [
                    self._edge_view(a, b, "out")
                    for a, b in zip(node_seq, node_seq[1:])
                ]
                results.append({"nodes": node_seq, "edges": hops})
                if len(results) >= max_paths:
                    break
        except nx.NetworkXNoPath:
            return []
        return results

    def blast_radius(self, node_id: str, depth: int = 2) -> list[dict]:
        """Nodes that depend on ``node_id`` (reverse reachability within depth),
        ranked by betweenness centrality descending."""
        if node_id not in self._g:
            raise KeyError(node_id)
        reverse = self._g.reverse(copy=False)
        lengths = nx.single_source_shortest_path_length(reverse, node_id, cutoff=depth)
        bc = self.betweenness()
        impacted = [
            {**self._node_view(nid), "distance": dist, "betweenness": bc.get(nid, 0.0)}
            for nid, dist in lengths.items()
            if nid != node_id
        ]
        impacted.sort(key=lambda n: n["betweenness"], reverse=True)
        return impacted

    def neighborhood(self, seeds: list[str], max_nodes: int = 30) -> dict:
        """BFS-expanded subgraph around seed nodes, capped at ``max_nodes``."""
        undirected = self._g.to_undirected(as_view=True)
        selected: list[str] = []
        seen: set[str] = set()
        frontier = [s for s in seeds if s in self._g]
        for s in frontier:
            if s not in seen:
                seen.add(s)
                selected.append(s)
        i = 0
        while i < len(selected) and len(selected) < max_nodes:
            for nbr in undirected.neighbors(selected[i]):
                if nbr not in seen:
                    seen.add(nbr)
                    selected.append(nbr)
                    if len(selected) >= max_nodes:
                        break
            i += 1
        node_set = set(selected)
        nodes = [self._node_view(n) for n in selected]
        edges = [
            self._edge_view(u, v, "out")
            for u, v in self._g.edges()
            if u in node_set and v in node_set
        ]
        return {"nodes": nodes, "edges": edges}

    # --- full-text search -------------------------------------------------

    def _build_fts(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE VIRTUAL TABLE fts USING fts5(kind, ref, text)"
        )
        rows = []
        for nid, attrs in self._g.nodes(data=True):
            text = " ".join(
                str(x)
                for x in (
                    attrs.get("label"),
                    attrs.get("source_file"),
                    attrs.get("community_name"),
                )
                if x
            )
            rows.append(("node", nid, text))
        for line in self._report_text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(("report", "GRAPH_REPORT.md", line))
        conn.executemany("INSERT INTO fts (kind, ref, text) VALUES (?, ?, ?)", rows)
        conn.commit()
        return conn

    def search(self, query: str, limit: int = 20) -> list[dict]:
        # sanitize to a safe FTS prefix query; bare tokens joined by OR
        tokens = [t for t in "".join(c if c.isalnum() else " " for c in query).split() if t]
        if not tokens:
            return []
        match = " OR ".join(f"{t}*" for t in tokens)
        cur = self._fts.execute(
            "SELECT kind, ref, text FROM fts WHERE fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (match, limit),
        )
        return [{"kind": k, "ref": r, "text": t} for k, r, t in cur.fetchall()]
