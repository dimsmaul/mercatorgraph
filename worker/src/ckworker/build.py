"""Build orchestration: lock -> clone/pull -> graphify -> validate -> stage -> promote.

PG-free by design: this returns an outcome; the caller (webhook layer) records the build row.
One writer per project via a per-slug lock. Validation aborts before promote, so a bad build
never replaces the live graph.
"""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from ckcommon.config import ProjectConfig

from ckworker.graphify_adapter import build_graph, load_counts
from ckworker.promote import current_out_dir, promote, stage_version

CloneFn = Callable[[str, str, Path], None]

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class ValidationError(Exception):
    """Raised when a fresh build fails validation; the live graph is left untouched."""


@dataclass(slots=True)
class BuildOutcome:
    version_ts: str
    node_count: int
    edge_count: int


def _lock_for(slug: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(slug, threading.Lock())


def default_clone(repo_url: str, branch: str, workdir: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(workdir)],
        check=True,
        capture_output=True,
        text=True,
    )


def _version_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def build_project(
    slug: str,
    config: ProjectConfig,
    data_dir: str | Path,
    *,
    clone_fn: CloneFn = default_clone,
    fixture: str | Path | None = None,
    retention: int = 5,
    drop_ratio: float = 0.5,
    force: bool = False,
) -> BuildOutcome:
    lock = _lock_for(slug)
    with lock:
        with TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "repo"
            clone_fn(config.repo_url, config.branch, workdir)

            result = build_graph(workdir, config.build_flags, fixture=fixture)

            if result.node_count <= 0:
                raise ValidationError("graph has no nodes")

            prev = current_out_dir(data_dir, slug)
            if prev is not None and not force:
                prev_nodes, _ = load_counts(prev)
                if prev_nodes > 0 and result.node_count < prev_nodes * drop_ratio:
                    raise ValidationError(
                        f"node count dropped {prev_nodes} -> {result.node_count}; "
                        "refusing to promote (use force)"
                    )

            version_ts = _version_ts()
            stage_version(data_dir, slug, version_ts, result.out_dir)
            promote(data_dir, slug, version_ts, retention=retention)
            return BuildOutcome(version_ts, result.node_count, result.edge_count)
