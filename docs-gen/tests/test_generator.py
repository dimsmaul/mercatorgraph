import json
from pathlib import Path

import pytest

from ckdocs import generate_project

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out"


def _read(p: Path) -> str:
    return p.read_text()


@pytest.fixture
def generated(tmp_path):
    out_root = tmp_path / "content" / "docs"
    written = generate_project(FIXTURE, "demo", "v1", out_root)
    return out_root, written


def test_creates_index_and_node_and_community(generated):
    out_root, _ = generated
    proj = out_root / "demo"
    assert (proj / "index.mdx").exists()
    assert (proj / "node" / "svc_db_conn.mdx").exists()
    assert list(proj.glob("community-*.mdx")), "expected community pages"
    assert (proj / "meta.json").exists()


def test_versions_json_written(generated):
    out_root, _ = generated
    versions = json.loads((out_root / "versions.json").read_text())
    assert versions["demo"] == "v1"


def test_node_frontmatter_and_edges(generated):
    out_root, _ = generated
    text = _read(out_root / "demo" / "node" / "svc_db_conn.mdx")
    assert text.startswith("---")
    assert "project: \"demo\"" in text
    assert "graph_version: \"v1\"" in text
    assert "confidence: \"EXTRACTED\"" in text
    # conn() has incoming callers rendered with confidence tag + permalink
    assert "[EXTRACTED]" in text
    assert "/docs/demo/node/" in text


def test_index_embeds_report_and_embed_component(generated):
    out_root, _ = generated
    text = _read(out_root / "demo" / "index.mdx")
    assert "Graph Report" in text  # embedded GRAPH_REPORT.md
    assert "<GraphEmbed" in text
    assert "project: \"demo\"" in text


def test_report_mdx_escaped(generated):
    out_root, _ = generated
    text = _read(out_root / "demo" / "index.mdx")
    # report contains "(<3 nodes)" which must be escaped so MDX doesn't parse JSX
    assert "&lt;3 nodes" in text
    # the raw hostile sequence must not survive in the embedded report body
    assert "(<3 nodes)" not in text


def test_community_links_to_nodes(generated):
    out_root, _ = generated
    comm = next((out_root / "demo").glob("community-*.mdx"))
    text = _read(comm)
    assert "/docs/demo/node/" in text


def test_regeneration_is_idempotent(tmp_path):
    out_root = tmp_path / "content" / "docs"
    generate_project(FIXTURE, "demo", "v1", out_root)
    first = sorted(p.name for p in (out_root / "demo" / "node").iterdir())
    generate_project(FIXTURE, "demo", "v2", out_root)
    second = sorted(p.name for p in (out_root / "demo" / "node").iterdir())
    assert first == second
    # version bumped
    assert json.loads((out_root / "versions.json").read_text())["demo"] == "v2"


def test_second_project_coexists(tmp_path):
    out_root = tmp_path / "content" / "docs"
    generate_project(FIXTURE, "demo", "v1", out_root)
    generate_project(FIXTURE, "other", "v1", out_root)
    assert (out_root / "demo" / "index.mdx").exists()
    assert (out_root / "other" / "index.mdx").exists()
    versions = json.loads((out_root / "versions.json").read_text())
    assert set(versions) == {"demo", "other"}
