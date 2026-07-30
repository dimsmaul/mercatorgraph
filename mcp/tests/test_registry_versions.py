import json
from pathlib import Path

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
