import textwrap

import pytest

from ckcommon.config import ProjectConfig, load_projects, resolve_secret


SAMPLE = textwrap.dedent(
    """
    projects:
      - slug: demo
        repo_url: https://github.com/octocat/Hello-World.git
        branch: master
        build_flags: ["--force"]
        webhook_secret_ref: WEBHOOK_SECRET_DEMO
      - slug: other
        repo_url: git@github.com:acme/other.git
        webhook_secret_ref: WEBHOOK_SECRET_OTHER
    """
)


@pytest.fixture
def projects_file(tmp_path):
    p = tmp_path / "projects.yaml"
    p.write_text(SAMPLE)
    return p


def test_load_projects_parses_all(projects_file):
    projects = load_projects(projects_file)
    assert set(projects) == {"demo", "other"}
    demo = projects["demo"]
    assert isinstance(demo, ProjectConfig)
    assert demo.repo_url.endswith("Hello-World.git")
    assert demo.branch == "master"
    assert demo.build_flags == ["--force"]
    assert demo.webhook_secret_ref == "WEBHOOK_SECRET_DEMO"


def test_defaults_applied(projects_file):
    other = load_projects(projects_file)["other"]
    assert other.branch == "main"        # default branch
    assert other.build_flags == []       # default empty


def test_rebuild_interval_parsed(tmp_path):
    p = tmp_path / "projects.yaml"
    p.write_text(
        textwrap.dedent(
            """
            projects:
              - slug: demo
                repo_url: https://x/demo.git
                rebuild_interval: 3600
              - slug: other
                repo_url: https://x/other.git
            """
        )
    )
    projects = load_projects(p)
    assert projects["demo"].rebuild_interval == 3600
    assert projects["other"].rebuild_interval is None


def test_resolve_secret_from_env(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_DEMO", "s3cr3t")
    assert resolve_secret("WEBHOOK_SECRET_DEMO") == "s3cr3t"


def test_resolve_secret_missing_returns_none(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    assert resolve_secret("NOPE") is None


def test_project_webhook_secret_helper(projects_file, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_DEMO", "abc")
    demo = load_projects(projects_file)["demo"]
    assert demo.webhook_secret() == "abc"
