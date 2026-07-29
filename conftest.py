import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent
FIXTURE_GRAPH_DIR = REPO_ROOT / "tests" / "fixtures" / "graphify-out"


@pytest.fixture
def fixture_graph_dir() -> Path:
    return FIXTURE_GRAPH_DIR


@pytest.fixture
def fixture_graph_json() -> dict:
    return json.loads((FIXTURE_GRAPH_DIR / "graph.json").read_text())
