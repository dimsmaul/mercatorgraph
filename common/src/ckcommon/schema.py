"""Typed models for graphify output.

Sole shared vocabulary for graph nodes and edges. graphify emits ``graph.json`` in
NetworkX node-link format; edges live under the ``links`` key. These models are tolerant
of missing optional fields and preserve unknown fields in ``extra`` so a graphify version
bump does not lose data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# graphify-out/ layout constants
GRAPHIFY_OUT_DIR = "graphify-out"
GRAPH_JSON = "graph.json"
REPORT_MD = "GRAPH_REPORT.md"

# top-level graph.json keys (NetworkX node-link)
NODES_KEY = "nodes"
LINKS_KEY = "links"


class Confidence(str, Enum):
    """Edge confidence. First three are emitted by graphify; CONTRIBUTED is reserved
    for the Fase 3 overlay layer and never appears inside graph.json."""

    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"
    CONTRIBUTED = "CONTRIBUTED"

    @classmethod
    def coerce(cls, value: object) -> "Confidence":
        try:
            return cls(str(value))
        except ValueError:
            return cls.INFERRED


# fields we lift into named attributes; everything else is kept in `extra`
_NODE_KNOWN = {
    "id",
    "label",
    "file_type",
    "source_file",
    "source_location",
    "community",
    "community_name",
    "norm_label",
    "_origin",
}
_EDGE_KNOWN = {
    "source",
    "target",
    "relation",
    "confidence",
    "confidence_score",
    "weight",
    "source_file",
    "source_location",
    "explanation",
    "_origin",
}


@dataclass(slots=True)
class GraphNode:
    id: str
    label: str
    file_type: str | None = None
    source_file: str | None = None
    source_location: str | None = None
    community: int | None = None
    community_name: str | None = None
    norm_label: str | None = None
    origin: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    relation: str
    confidence: Confidence = Confidence.INFERRED
    confidence_score: float | None = None
    weight: float | None = None
    source_file: str | None = None
    source_location: str | None = None
    explanation: str | None = None
    origin: str | None = None
    extra: dict = field(default_factory=dict)


def parse_node(raw: dict) -> GraphNode:
    extra = {k: v for k, v in raw.items() if k not in _NODE_KNOWN}
    return GraphNode(
        id=raw["id"],
        label=raw.get("label", raw["id"]),
        file_type=raw.get("file_type"),
        source_file=raw.get("source_file"),
        source_location=raw.get("source_location"),
        community=raw.get("community"),
        community_name=raw.get("community_name"),
        norm_label=raw.get("norm_label"),
        origin=raw.get("_origin"),
        extra=extra,
    )


def parse_edge(raw: dict) -> GraphEdge:
    extra = {k: v for k, v in raw.items() if k not in _EDGE_KNOWN}
    return GraphEdge(
        source=raw["source"],
        target=raw["target"],
        relation=raw.get("relation", "related"),
        confidence=Confidence.coerce(raw.get("confidence")),
        confidence_score=raw.get("confidence_score"),
        weight=raw.get("weight"),
        source_file=raw.get("source_file"),
        source_location=raw.get("source_location"),
        explanation=raw.get("explanation"),
        origin=raw.get("_origin"),
        extra=extra,
    )


def parse_graph(data: dict) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Parse a graphify node-link graph.json dict into typed nodes and edges."""
    nodes = [parse_node(n) for n in data.get(NODES_KEY, [])]
    edges = [parse_edge(e) for e in data.get(LINKS_KEY, [])]
    return nodes, edges
