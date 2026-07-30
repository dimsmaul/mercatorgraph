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
    new = json.loads(json.dumps(old))
    new["nodes"] = [n for n in new["nodes"] if n["id"] != "svc_db_conn"]
    new["links"] = [
        e for e in new["links"]
        if e["source"] != "svc_db_conn" and e["target"] != "svc_db_conn"
    ]
    d = diff_graphs(old, new)
    removed_ids = {n["id"] for n in d["nodes_removed"]}
    assert "svc_db_conn" in removed_ids
    assert d["counts"]["edges_removed"] > 0
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
