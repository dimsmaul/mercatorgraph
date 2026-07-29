"""Sole owner of graphify knowledge.

The valuable graphify IP is *extraction* (tree-sitter AST -> graph). We delegate it 100% via
`graphify update <path>`, which is headless and needs no LLM/API key. Everything the rest of
the platform knows about graphify's output format goes through here, so a version bump
touches one file. Version is pinned in the worker Dockerfile (0.9.28 at time of writing).

`fixture` mode copies a prebuilt graphify-out/ instead of invoking the CLI — used by tests
and offline development so the pipeline is exercisable without a network clone.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ckcommon.schema import GRAPH_JSON, GRAPHIFY_OUT_DIR, parse_graph

GRAPHIFY_BIN = os.environ.get("GRAPHIFY_BIN", "graphify")


@dataclass(slots=True)
class BuildResult:
    out_dir: Path
    node_count: int
    edge_count: int


def load_counts(graphify_out_dir: str | Path) -> tuple[int, int]:
    data = json.loads((Path(graphify_out_dir) / GRAPH_JSON).read_text())
    nodes, edges = parse_graph(data)
    return len(nodes), len(edges)


def build_graph(
    repo_dir: str | Path,
    extra_flags: list[str] | None = None,
    fixture: str | Path | None = None,
) -> BuildResult:
    """Produce a graphify-out/ inside ``repo_dir`` and return its node/edge counts.

    Real mode runs ``graphify update .`` (no LLM). Fixture mode copies a prebuilt output.
    """
    repo_dir = Path(repo_dir)
    out = repo_dir / GRAPHIFY_OUT_DIR

    if fixture is not None:
        out.mkdir(parents=True, exist_ok=True)
        shutil.copytree(fixture, out, dirs_exist_ok=True)
    else:
        cmd = [GRAPHIFY_BIN, "update", ".", *(extra_flags or [])]
        subprocess.run(
            cmd, cwd=str(repo_dir), check=True, capture_output=True, text=True
        )

    graph_path = out / GRAPH_JSON
    if not graph_path.exists():
        raise RuntimeError(f"graphify produced no {GRAPH_JSON} in {out}")
    nc, ec = load_counts(out)
    return BuildResult(out_dir=out, node_count=nc, edge_count=ec)
