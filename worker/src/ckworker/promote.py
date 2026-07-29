"""Staging + atomic promote + retention on the shared volume.

Layout:
    <data>/projects/<slug>/versions/<ts>/graphify-out/
    <data>/projects/<slug>/current -> versions/<ts>   (symlink)

Promote flips the ``current`` symlink with ``os.replace`` (atomic rename), so an agent never
observes a half-built graph.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ckcommon.schema import GRAPHIFY_OUT_DIR


def project_dir(data_dir: str | Path, slug: str) -> Path:
    return Path(data_dir) / "projects" / slug


def current_out_dir(data_dir: str | Path, slug: str) -> Path | None:
    cur = project_dir(data_dir, slug) / "current"
    if not cur.exists():
        return None
    return cur / GRAPHIFY_OUT_DIR


def stage_version(
    data_dir: str | Path, slug: str, version_ts: str, source_out_dir: str | Path
) -> Path:
    """Copy a freshly built graphify-out/ into its versioned home. Returns the version dir."""
    version_dir = project_dir(data_dir, slug) / "versions" / version_ts
    dest_out = version_dir / GRAPHIFY_OUT_DIR
    dest_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_out_dir, dest_out)
    return version_dir


def promote(data_dir: str | Path, slug: str, version_ts: str, retention: int = 5) -> None:
    proj = project_dir(data_dir, slug)
    current = proj / "current"
    tmp = proj / ".current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("versions") / version_ts)
    os.replace(tmp, current)  # atomic symlink swap
    prune_versions(proj, keep=retention)


def prune_versions(proj: Path, keep: int) -> None:
    versions_dir = proj / "versions"
    if not versions_dir.exists():
        return
    current = proj / "current"
    keep_target = None
    if current.exists():
        keep_target = (versions_dir / Path(os.readlink(current)).name).resolve()

    dirs = sorted([d for d in versions_dir.iterdir() if d.is_dir()])
    for d in dirs[:-keep] if keep > 0 else []:
        if keep_target is not None and d.resolve() == keep_target:
            continue
        shutil.rmtree(d)
