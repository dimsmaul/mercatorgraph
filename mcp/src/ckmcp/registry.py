"""Filesystem-backed graph registry with hot-reload.

Layout on the shared volume:
    <data>/projects/<slug>/versions/<ts>/graphify-out/graph.json
    <data>/projects/<slug>/current -> versions/<ts>     (symlink)

``get`` resolves the ``current`` symlink and caches the loaded GraphStore keyed by its
target. When the worker promotes a new version (flips the symlink), the next ``get`` sees a
new target and rebuilds the store, swapping the cache entry atomically. In-flight callers
keep their already-returned store.
"""

from __future__ import annotations

import os
from pathlib import Path

import json

from ckcommon.schema import GRAPH_JSON, GRAPHIFY_OUT_DIR
from ckmcp.graphstore import GraphStore


class FsGraphRegistry:
    def __init__(self, data_dir: str | Path) -> None:
        self._root = Path(data_dir) / "projects"
        self._cache: dict[str, tuple[str, GraphStore]] = {}

    def _current(self, slug: str) -> Path:
        return self._root / slug / "current"

    def has(self, slug: str) -> bool:
        return self._current(slug).exists()

    def get(self, slug: str) -> GraphStore:
        current = self._current(slug)
        if not current.exists():
            raise KeyError(f"project {slug!r} not indexed")
        target = os.readlink(current)
        cached = self._cache.get(slug)
        if cached is not None and cached[0] == target:
            return cached[1]
        store = GraphStore.from_dir(current / GRAPHIFY_OUT_DIR)
        self._cache[slug] = (target, store)  # atomic swap
        return store

    def list_slugs(self) -> list[str]:
        if not self._root.exists():
            return []
        return [p.name for p in self._root.iterdir() if (p / "current").exists()]

    def _versions_dir(self, slug: str) -> Path:
        return self._root / slug / "versions"

    def list_versions(self, slug: str) -> list[str]:
        vdir = self._versions_dir(slug)
        if not vdir.exists():
            return []
        return sorted(p.name for p in vdir.iterdir() if p.is_dir())

    def load_version_json(self, slug: str, version: str) -> dict:
        path = self._versions_dir(slug) / version / GRAPHIFY_OUT_DIR / GRAPH_JSON
        if not path.exists():
            raise KeyError(f"version {version!r} of {slug!r} not found")
        return json.loads(path.read_text())
