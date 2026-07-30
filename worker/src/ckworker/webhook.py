"""FastAPI worker: webhook (primary trigger), manual rebuild, build status.

Builds run in a background task that records a ``builds`` row (running -> succeeded/failed).
The builder is injectable so tests can drive the pipeline in fixture mode without git/network.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Callable

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from psycopg_pool import ConnectionPool

from ckcommon.config import ProjectConfig
from ckworker.build import BuildOutcome, build_project
from ckworker.cron import CronScheduler
from ckworker.notify import Notifier
from ckworker.debounce import BuildDebouncer
from ckworker.promote import current_out_dir

Builder = Callable[[str, ProjectConfig, bool], BuildOutcome]


def verify_signature(secret: str | None, body: bytes, header: str | None) -> bool:
    """GitHub-style HMAC-SHA256 signature check (`X-Hub-Signature-256: sha256=...`)."""
    if not secret or not header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def make_default_builder(data_dir: str) -> Builder:
    def _build(slug: str, config: ProjectConfig, force: bool) -> BuildOutcome:
        return build_project(slug, config, data_dir, force=force)

    return _build


def run_build_and_record(
    pool: ConnectionPool,
    slug: str,
    builder: Builder,
    config: ProjectConfig,
    force: bool,
    notifier: "Notifier | None" = None,
) -> None:
    with pool.connection() as conn:
        build_id = conn.execute(
            "INSERT INTO builds (project_slug, version_ts, status) "
            "VALUES (%s, %s, 'running') RETURNING id",
            (slug, "pending"),
        ).fetchone()[0]
        conn.commit()
    try:
        outcome = builder(slug, config, force)
    except Exception as exc:  # noqa: BLE001 — record failure, keep live graph
        with pool.connection() as conn:
            conn.execute(
                "UPDATE builds SET status='failed', error=%s, finished_at=now() "
                "WHERE id=%s",
                (str(exc), build_id),
            )
            conn.commit()
        return
    with pool.connection() as conn:
        conn.execute(
            "UPDATE builds SET status='succeeded', version_ts=%s, node_count=%s, "
            "edge_count=%s, finished_at=now() WHERE id=%s",
            (outcome.version_ts, outcome.node_count, outcome.edge_count, build_id),
        )
        conn.commit()
    if notifier is not None:
        notifier.notify(
            {
                "event": "build.succeeded",
                "project": slug,
                "version_ts": outcome.version_ts,
                "node_count": outcome.node_count,
                "edge_count": outcome.edge_count,
            }
        )


def create_app(
    pool: ConnectionPool,
    data_dir: str,
    projects: dict[str, ProjectConfig],
    builder: Builder | None = None,
    debounce_seconds: float = 0.0,
    start_cron: bool = False,
    notify_url: str | None = None,
) -> FastAPI:
    builder = builder or make_default_builder(data_dir)
    notifier = Notifier(notify_url)
    app = FastAPI(title="centralize-knowledge worker")

    # coalesce bursts of webhook pushes per project (PRD open-Q1). Off at <= 0.
    debouncer: BuildDebouncer | None = None
    if debounce_seconds > 0:
        debouncer = BuildDebouncer(
            debounce_seconds,
            lambda slug: run_build_and_record(
                pool, slug, builder, projects[slug], False, notifier
            ),
        )
        app.state.debouncer = debouncer

    # docs app (different origin) calls /status + /graph.html from the browser
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("WORKER_CORS_ORIGINS", "*").split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # interval-based rebuilds (PRD 'cron' trigger)
    if start_cron:
        cron = CronScheduler(
            lambda slug: run_build_and_record(
                pool, slug, builder, projects[slug], False, notifier
            )
        )
        app.state.cron = cron

        @app.on_event("startup")
        def _start_cron() -> None:
            for slug, cfg in projects.items():
                if cfg.rebuild_interval:
                    cron.schedule(slug, cfg.rebuild_interval)

        @app.on_event("shutdown")
        def _stop_cron() -> None:
            cron.stop()

    def _config(slug: str) -> ProjectConfig:
        cfg = projects.get(slug)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"unknown project {slug!r}")
        return cfg

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/webhook/{slug}")
    async def webhook(slug: str, request: Request, background: BackgroundTasks):
        cfg = _config(slug)
        body = await request.body()
        sig = request.headers.get("X-Hub-Signature-256")
        if not verify_signature(cfg.webhook_secret(), body, sig):
            raise HTTPException(status_code=401, detail="bad signature")
        if debouncer is not None:
            debouncer.trigger(slug)  # coalesce bursts
        else:
            background.add_task(
                run_build_and_record, pool, slug, builder, cfg, False, notifier
            )
        return JSONResponse({"status": "accepted", "project": slug}, status_code=202)

    @app.post("/projects/{slug}/rebuild")
    def rebuild(slug: str, background: BackgroundTasks, force: bool = False):
        cfg = _config(slug)
        background.add_task(
            run_build_and_record, pool, slug, builder, cfg, force, notifier
        )
        return JSONResponse({"status": "accepted", "project": slug}, status_code=202)

    @app.get("/projects/{slug}/graph.html")
    def graph_html(slug: str):
        """Serve graphify's interactive graph.html for the docs-app embed."""
        _config(slug)
        out = current_out_dir(data_dir, slug)
        if out is None or not (out / "graph.html").exists():
            raise HTTPException(status_code=404, detail="no graph.html")
        return FileResponse(out / "graph.html", media_type="text/html")

    @app.get("/projects/{slug}/status")
    def status(slug: str) -> dict:
        _config(slug)
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT version_ts, status, node_count, edge_count, error, "
                "started_at, finished_at FROM builds WHERE project_slug=%s "
                "ORDER BY started_at DESC LIMIT 1",
                (slug,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="no builds yet")
        return {
            "project": slug,
            "version_ts": row[0],
            "status": row[1],
            "node_count": row[2],
            "edge_count": row[3],
            "error": row[4],
            "started_at": row[5].isoformat() if row[5] else None,
            "finished_at": row[6].isoformat() if row[6] else None,
        }

    @app.get("/stats/builds")
    def stats_builds() -> dict:
        """Per-project build counts by status + last successful build time."""
        with pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT project_slug,
                       count(*) AS total,
                       count(*) FILTER (WHERE status='succeeded') AS succeeded,
                       count(*) FILTER (WHERE status='failed') AS failed,
                       max(finished_at) FILTER (WHERE status='succeeded') AS last_ok
                FROM builds GROUP BY project_slug ORDER BY project_slug
                """
            ).fetchall()
        return {
            "projects": [
                {
                    "slug": slug,
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                    "last_build_at": last_ok.isoformat() if last_ok else None,
                }
                for slug, total, succeeded, failed, last_ok in rows
            ]
        }

    @app.get("/stats/usage")
    def stats_usage() -> dict:
        """MCP tool usage counts from the audit log."""
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT tool, count(*) FROM audit_log GROUP BY tool ORDER BY count(*) DESC"
            ).fetchall()
        tools = [{"tool": tool, "count": count} for tool, count in rows]
        return {"tools": tools, "total": sum(t["count"] for t in tools)}

    return app


def main() -> None:
    import uvicorn

    from ckcommon.db import apply_migrations, get_pool
    from ckworker.registry import all_projects

    pool = get_pool()
    # worker owns DB writes -> it applies migrations on startup (idempotent)
    apply_migrations(pool, os.environ.get("MIGRATIONS_DIR", "db/migrations"))
    data_dir = os.environ.get("DATA_DIR", "/data")
    debounce = float(os.environ.get("DEBOUNCE_SECONDS", "0"))
    app = create_app(
        pool,
        data_dir,
        all_projects(),
        debounce_seconds=debounce,
        start_cron=True,
        notify_url=os.environ.get("NOTIFY_URL"),
    )
    uvicorn.run(app, host=os.environ.get("WORKER_HOST", "0.0.0.0"),
                port=int(os.environ.get("WORKER_PORT", "8000")))


if __name__ == "__main__":
    main()
