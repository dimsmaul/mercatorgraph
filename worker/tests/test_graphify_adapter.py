import shutil
from pathlib import Path

import pytest

from ckworker.graphify_adapter import build_graph, load_counts

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out"


def test_load_counts(tmp_path):
    dst = tmp_path / "graphify-out"
    shutil.copytree(FIXTURE, dst)
    assert load_counts(dst) == (9, 18)


def test_build_graph_fixture_mode(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    res = build_graph(repo, fixture=FIXTURE)
    assert res.out_dir == repo / "graphify-out"
    assert (res.out_dir / "graph.json").exists()
    assert res.node_count == 9
    assert res.edge_count == 18


@pytest.mark.skipif(shutil.which("graphify") is None, reason="graphify not installed")
def test_build_graph_real_cli(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "mod.py").write_text("def a():\n    return b()\n\ndef b():\n    return 1\n")
    res = build_graph(repo)
    assert res.node_count > 0
    assert (res.out_dir / "graph.json").exists()
