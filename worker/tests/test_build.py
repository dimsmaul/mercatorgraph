import json
import os
from pathlib import Path

import pytest

from ckcommon.config import ProjectConfig
from ckcommon.schema import GRAPHIFY_OUT_DIR
from ckworker.build import BuildOutcome, ValidationError, build_project
from ckworker.promote import current_out_dir, promote, stage_version

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out"


def noop_clone(repo_url, branch, workdir):
    Path(workdir).mkdir(parents=True, exist_ok=True)


@pytest.fixture
def config():
    return ProjectConfig(slug="demo", repo_url="https://x/demo.git", branch="main")


def _small_fixture(tmp_path, n_nodes):
    graph = json.loads((FIXTURE / "graph.json").read_text())
    graph = {**graph, "nodes": graph["nodes"][:n_nodes], "links": []}
    d = tmp_path / f"fix{n_nodes}" / GRAPHIFY_OUT_DIR
    d.mkdir(parents=True)
    (d / "graph.json").write_text(json.dumps(graph))
    return d


def test_build_creates_version_and_current(tmp_path, config):
    data = tmp_path / "data"
    out = build_project("demo", config, data, clone_fn=noop_clone, fixture=FIXTURE)
    assert isinstance(out, BuildOutcome)
    assert out.node_count == 9
    current = data / "projects" / "demo" / "current"
    assert current.is_symlink()
    assert (current / GRAPHIFY_OUT_DIR / "graph.json").exists()


def test_second_build_promotes_new_version(tmp_path, config):
    data = tmp_path / "data"
    build_project("demo", config, data, clone_fn=noop_clone, fixture=FIXTURE)
    out2 = build_project("demo", config, data, clone_fn=noop_clone, fixture=FIXTURE)
    target = os.readlink(data / "projects" / "demo" / "current")
    assert out2.version_ts in target


def test_validation_aborts_on_big_drop_keeps_current(tmp_path, config):
    data = tmp_path / "data"
    build_project("demo", config, data, clone_fn=noop_clone, fixture=FIXTURE)
    good_target = os.readlink(data / "projects" / "demo" / "current")

    tiny = _small_fixture(tmp_path, 2)  # 2 << 9*0.5 -> abort
    with pytest.raises(ValidationError):
        build_project("demo", config, data, clone_fn=noop_clone, fixture=tiny)

    # current unchanged
    assert os.readlink(data / "projects" / "demo" / "current") == good_target
    assert current_out_dir(data, "demo") is not None


def test_force_allows_drop(tmp_path, config):
    data = tmp_path / "data"
    build_project("demo", config, data, clone_fn=noop_clone, fixture=FIXTURE)
    tiny = _small_fixture(tmp_path, 2)
    out = build_project(
        "demo", config, data, clone_fn=noop_clone, fixture=tiny, force=True
    )
    assert out.node_count == 2


def test_retention_prunes_old_versions(tmp_path):
    proj = tmp_path / "projects" / "demo"
    # stage 4 versions, keep=2
    for i in range(4):
        ver = f"v{i}"
        stage_version(tmp_path, "demo", ver, FIXTURE)
        promote(tmp_path, "demo", ver, retention=2)
    versions = sorted(d.name for d in (proj / "versions").iterdir())
    assert len(versions) == 2
    # newest kept, current intact
    assert (proj / "current" / GRAPHIFY_OUT_DIR / "graph.json").exists()
