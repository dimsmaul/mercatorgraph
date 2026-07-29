from pathlib import Path

import pytest

from ckcommon.schema import Confidence
from ckmcp.graphstore import GraphStore

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out"


@pytest.fixture
def store() -> GraphStore:
    return GraphStore.from_dir(FIXTURE)


def test_load_counts(store):
    assert store.node_count == 9
    assert store.edge_count == 18


def test_node_detail(store):
    d = store.node_detail("svc_db_conn")
    assert d["id"] == "svc_db_conn"
    assert d["label"] == "conn()"
    assert d["source_file"] == "svc/db.py"
    # direct edges present, each carrying relation + confidence
    assert d["edges"], "expected direct edges"
    for e in d["edges"]:
        assert "relation" in e
        assert e["confidence"] in {c.value for c in Confidence}
        assert e["direction"] in {"in", "out"}
    # conn has incoming callers
    assert any(e["direction"] == "in" for e in d["edges"])


def test_node_detail_unknown_raises(store):
    with pytest.raises(KeyError):
        store.node_detail("does_not_exist")


def test_trace_path(store):
    paths = store.paths("svc_api_handle", "svc_db_conn", max_paths=1)
    assert paths
    p = paths[0]
    assert p["nodes"][0] == "svc_api_handle"
    assert p["nodes"][-1] == "svc_db_conn"
    # each hop explained
    for edge in p["edges"]:
        assert edge["relation"]
        assert edge["confidence"] in {c.value for c in Confidence}


def test_trace_path_no_route_returns_empty(store):
    # conn has no outgoing edges -> cannot reach handle
    assert store.paths("svc_db_conn", "svc_api_handle") == []


def test_blast_radius_finds_dependents(store):
    impacted = store.blast_radius("svc_db_conn", depth=2)
    ids = {n["id"] for n in impacted}
    # direct dependents of conn
    assert {"svc_db_save", "svc_auth_verify"} <= ids
    # ranked by betweenness (descending)
    scores = [n["betweenness"] for n in impacted]
    assert scores == sorted(scores, reverse=True)


def test_blast_radius_respects_depth(store):
    d1 = {n["id"] for n in store.blast_radius("svc_db_conn", depth=1)}
    d2 = {n["id"] for n in store.blast_radius("svc_db_conn", depth=2)}
    assert d1 <= d2
    assert len(d2) >= len(d1)


def test_neighborhood_caps_nodes(store):
    sub = store.neighborhood(["svc_db_conn"], max_nodes=3)
    assert len(sub["nodes"]) <= 3
    assert any(n["id"] == "svc_db_conn" for n in sub["nodes"])


def test_search_matches_label(store):
    hits = store.search("conn", limit=5)
    assert any(h["ref"] == "svc_db_conn" for h in hits)


def test_search_respects_limit(store):
    hits = store.search("svc", limit=2)
    assert len(hits) <= 2


def test_betweenness_cached(store):
    a = store.betweenness()
    b = store.betweenness()
    assert a is b  # same object, computed once
