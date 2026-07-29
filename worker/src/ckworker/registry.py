"""Project registry lookup for the worker (thin wrapper over ckcommon.config)."""

from __future__ import annotations

import os
from pathlib import Path

from ckcommon.config import ProjectConfig, load_projects


def _config_path(config_path: str | Path | None) -> Path:
    path = config_path or os.environ.get("PROJECTS_CONFIG", "projects.yaml")
    return Path(path)


def all_projects(config_path: str | Path | None = None) -> dict[str, ProjectConfig]:
    return load_projects(_config_path(config_path))


def get_project(slug: str, config_path: str | Path | None = None) -> ProjectConfig:
    projects = all_projects(config_path)
    if slug not in projects:
        raise KeyError(f"project {slug!r} not registered")
    return projects[slug]
