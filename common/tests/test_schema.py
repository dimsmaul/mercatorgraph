from ckcommon.schema import (
    GRAPH_JSON,
    GRAPHIFY_OUT_DIR,
    REPORT_MD,
    Confidence,
    GraphEdge,
    GraphNode,
    parse_edge,
    parse_node,
    parse_graph,
)


def test_layout_constants():
    assert GRAPHIFY_OUT_DIR == "graphify-out"
    assert GRAPH_JSON == "graph.json"
    assert REPORT_MD == "GRAPH_REPORT.md"


def test_confidence_has_three_tags_plus_contributed():
    assert Confidence("EXTRACTED") is Confidence.EXTRACTED
    assert Confidence("INFERRED") is Confidence.INFERRED
    assert Confidence("AMBIGUOUS") is Confidence.AMBIGUOUS
    # reserved for Fase 3 overlay, never emitted by graphify
    assert Confidence.CONTRIBUTED.value == "CONTRIBUTED"


def test_parse_node_real_fields():
    raw = {
        "id": "svc_db_conn",
        "label": "conn()",
        "file_type": "code",
        "source_file": "svc/db.py",
        "source_location": "L4",
        "community": 1,
        "community_name": "svc.db",
        "norm_label": "conn()",
        "_origin": "ast",
    }
    n = parse_node(raw)
    assert n.id == "svc_db_conn"
    assert n.label == "conn()"
    assert n.file_type == "code"
    assert n.source_file == "svc/db.py"
    assert n.source_location == "L4"
    assert n.community == 1
    assert n.community_name == "svc.db"
    assert n.origin == "ast"


def test_parse_node_tolerates_missing_optionals():
    n = parse_node({"id": "x", "label": "x"})
    assert n.id == "x"
    assert n.community is None
    assert n.community_name is None
    assert n.source_location is None


def test_parse_edge_real_fields():
    raw = {
        "source": "svc_api_handle",
        "target": "svc_auth_verify",
        "relation": "calls",
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "weight": 1.0,
        "source_file": "svc/api.py",
        "source_location": "L5",
        "_origin": "ast",
    }
    e = parse_edge(raw)
    assert e.source == "svc_api_handle"
    assert e.target == "svc_auth_verify"
    assert e.relation == "calls"
    assert e.confidence is Confidence.EXTRACTED
    assert e.confidence_score == 1.0


def test_parse_edge_unknown_confidence_falls_back():
    e = parse_edge({"source": "a", "target": "b", "relation": "x"})
    # missing confidence -> default INFERRED, does not raise
    assert isinstance(e.confidence, Confidence)


def test_parse_graph_from_fixture(fixture_graph_json):
    nodes, edges = parse_graph(fixture_graph_json)
    assert len(nodes) == 9
    assert len(edges) == 18
    assert all(isinstance(n, GraphNode) for n in nodes)
    assert all(isinstance(e, GraphEdge) for e in edges)
    # fixture is 100% EXTRACTED
    assert {e.confidence for e in edges} == {Confidence.EXTRACTED}
