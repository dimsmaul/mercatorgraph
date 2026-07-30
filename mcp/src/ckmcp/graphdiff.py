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
