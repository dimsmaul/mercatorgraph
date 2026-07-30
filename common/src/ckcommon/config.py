"""Project registry config.

Loads ``projects.yaml``. Secrets are referenced by env var name and resolved at use time,
never inlined into the config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_BRANCH = "main"


def resolve_secret(ref: str | None) -> str | None:
    """Resolve a secret by env var name. Returns None if unset."""
    if not ref:
        return None
    return os.environ.get(ref)


@dataclass(slots=True)
class ProjectConfig:
    slug: str
    repo_url: str
    branch: str = DEFAULT_BRANCH
    build_flags: list[str] = field(default_factory=list)
    webhook_secret_ref: str | None = None
    rebuild_interval: int | None = None
    deploy_key_ref: str | None = None  # path to an encrypted SSH deploy key

    def webhook_secret(self) -> str | None:
        return resolve_secret(self.webhook_secret_ref)


def _project_from_dict(raw: dict) -> ProjectConfig:
    return ProjectConfig(
        slug=raw["slug"],
        repo_url=raw["repo_url"],
        branch=raw.get("branch") or DEFAULT_BRANCH,
        build_flags=list(raw.get("build_flags") or []),
        webhook_secret_ref=raw.get("webhook_secret_ref"),
        rebuild_interval=raw.get("rebuild_interval"),
        deploy_key_ref=raw.get("deploy_key_ref"),
    )


def load_projects(path: str | Path) -> dict[str, ProjectConfig]:
    """Load projects.yaml into a slug -> ProjectConfig mapping."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    projects = [_project_from_dict(p) for p in data.get("projects", [])]
    return {p.slug: p for p in projects}
