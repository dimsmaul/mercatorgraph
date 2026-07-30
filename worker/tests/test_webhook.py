import hashlib
import hmac
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ckcommon.config import ProjectConfig
from ckcommon.db import apply_migrations
from ckcommon.schema import GRAPHIFY_OUT_DIR
from ckworker.build import build_project
from ckworker.webhook import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "db" / "migrations"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "graphify-out"
SECRET = "hook-secret"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set"
)


def noop_clone(repo_url, branch, workdir):
    Path(workdir).mkdir(parents=True, exist_ok=True)


@pytest.fixture
def pool():
    from psycopg_pool import ConnectionPool

    p = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=4, open=True)
    with p.connection() as conn:
        conn.execute(
            "DROP TABLE IF EXISTS annotations, audit_log, tokens, builds, projects, "
            "schema_migrations CASCADE"
        )
        conn.commit()
    apply_migrations(p, MIGRATIONS)
    with p.connection() as conn:
        conn.execute(
            "INSERT INTO projects (slug, repo_url) VALUES ('demo', 'https://x/demo.git')"
        )
        conn.commit()
    yield p
    p.close()


@pytest.fixture
def client(pool, tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_DEMO", SECRET)
    data_dir = str(tmp_path / "data")
    cfg = ProjectConfig(
        slug="demo",
        repo_url="https://x/demo.git",
        branch="main",
        webhook_secret_ref="WEBHOOK_SECRET_DEMO",
    )

    def builder(slug, config, force):
        return build_project(
            slug, config, data_dir, clone_fn=noop_clone, fixture=FIXTURE, force=force
        )

    app = create_app(pool, data_dir, {"demo": cfg}, builder=builder)
    return TestClient(app), data_dir, pool


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_health(client):
    tc, _, _ = client
    assert tc.get("/health").json() == {"status": "ok"}


def test_cors_header_present(client):
    tc, _, _ = client
    r = tc.get("/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") in {"*", "http://localhost:3000"}


def test_webhook_bad_signature_rejected(client):
    tc, _, _ = client
    r = tc.post("/webhook/demo", content=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"})
    assert r.status_code == 401


def test_webhook_valid_signature_triggers_build(client):
    tc, data_dir, pool = client
    body = b'{"ref":"refs/heads/main"}'
    r = tc.post("/webhook/demo", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    assert r.status_code == 202
    # background task ran -> build row succeeded + current symlink present
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT status, node_count FROM builds WHERE project_slug='demo' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    assert row[0] == "succeeded"
    assert row[1] == 9
    current = Path(data_dir) / "projects" / "demo" / "current"
    assert (current / GRAPHIFY_OUT_DIR / "graph.json").exists()


def test_manual_rebuild(client):
    tc, _, pool = client
    r = tc.post("/projects/demo/rebuild")
    assert r.status_code == 202
    with pool.connection() as conn:
        n = conn.execute("SELECT count(*) FROM builds WHERE status='succeeded'").fetchone()
    assert n[0] >= 1


def test_status_returns_latest(client):
    tc, _, _ = client
    body = b"{}"
    tc.post("/webhook/demo", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    r = tc.get("/projects/demo/status")
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"
    assert r.json()["node_count"] == 9


def test_unknown_project_404(client):
    tc, _, _ = client
    assert tc.post("/projects/nope/rebuild").status_code == 404
    assert tc.get("/projects/nope/status").status_code == 404


def test_build_sends_notification(pool, tmp_path):
    from ckworker.notify import Notifier
    from ckworker.webhook import run_build_and_record

    data_dir = str(tmp_path / "data")
    cfg = ProjectConfig(slug="demo", repo_url="https://x/demo.git", branch="main")

    def builder(slug, config, force):
        return build_project(
            slug, config, data_dir, clone_fn=noop_clone, fixture=FIXTURE, force=force
        )

    sent = []
    notifier = Notifier("http://hook", poster=lambda url, payload: sent.append(payload))
    run_build_and_record(pool, "demo", builder, cfg, False, notifier)

    assert sent, "expected a notification"
    assert sent[0]["event"] == "build.succeeded"
    assert sent[0]["project"] == "demo"
    assert sent[0]["node_count"] == 9


def test_cron_triggers_rebuild(pool, tmp_path, monkeypatch):
    data_dir = str(tmp_path / "data")
    cfg = ProjectConfig(
        slug="demo", repo_url="https://x/demo.git", branch="main", rebuild_interval=0.15
    )

    def builder(slug, config, force):
        return build_project(
            slug, config, data_dir, clone_fn=noop_clone, fixture=FIXTURE, force=force
        )

    app = create_app(pool, data_dir, {"demo": cfg}, builder=builder, start_cron=True)
    with TestClient(app):  # startup schedules cron; shutdown stops it
        deadline = time.time() + 5
        n = 0
        while time.time() < deadline:
            with pool.connection() as conn:
                n = conn.execute(
                    "SELECT count(*) FROM builds WHERE project_slug='demo' "
                    "AND status='succeeded'"
                ).fetchone()[0]
            if n >= 1:
                break
            time.sleep(0.05)
    assert n >= 1


def test_graph_html_404_when_absent(client):
    tc, _, _ = client
    tc.post("/projects/demo/rebuild")  # fixture has no graph.html
    assert tc.get("/projects/demo/graph.html").status_code == 404


def test_webhook_debounce_coalesces_bursts(pool, tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_DEMO", SECRET)
    data_dir = str(tmp_path / "data")
    cfg = ProjectConfig(
        slug="demo",
        repo_url="https://x/demo.git",
        branch="main",
        webhook_secret_ref="WEBHOOK_SECRET_DEMO",
    )

    def builder(slug, config, force):
        return build_project(
            slug, config, data_dir, clone_fn=noop_clone, fixture=FIXTURE, force=force
        )

    app = create_app(pool, data_dir, {"demo": cfg}, builder=builder, debounce_seconds=0.4)
    tc = TestClient(app)
    body = b'{"ref":"refs/heads/main"}'
    sig = _sign(body)

    for _ in range(3):  # burst within the window
        tc.post("/webhook/demo", content=body, headers={"X-Hub-Signature-256": sig})
        time.sleep(0.05)

    # wait deterministically for the single coalesced build to finish (no leaked thread)
    def _succeeded() -> int:
        with pool.connection() as conn:
            return conn.execute(
                "SELECT count(*) FROM builds WHERE project_slug='demo' "
                "AND status='succeeded'"
            ).fetchone()[0]

    deadline = time.time() + 5
    n = 0
    while time.time() < deadline:
        n = _succeeded()
        if n >= 1:
            break
        time.sleep(0.05)
    app.state.debouncer.flush()

    assert n == 1  # three pushes coalesced into one build
    time.sleep(0.2)
    assert _succeeded() == 1  # no second build fires after coalescing


def test_graph_html_served_when_present(client):
    tc, data_dir, _ = client
    tc.post("/projects/demo/rebuild")
    out = Path(data_dir) / "projects" / "demo" / "current" / GRAPHIFY_OUT_DIR
    (out / "graph.html").write_text("<html><body>graph</body></html>")
    r = tc.get("/projects/demo/graph.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "graph" in r.text
