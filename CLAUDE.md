# CLAUDE.md — Centralized Codebase Knowledge Platform

Repo conventions for this project. Read before editing.

## What this is

Self-hosted platform that wraps **Graphify** to build one centralized, read-only
knowledge graph per project, served to many AI agents through a single MCP server.

Design source of truth: `PRD.md` + `docs/superpowers/specs/`.
Architecture + data flow: `flow.md`.

## Hard rules

1. **Graphify is a dependency, not a fork.** Never modify Graphify internals. We only
   consume its `graphify-out/` output. All Graphify knowledge lives in ONE module:
   `worker/src/worker/graphify_adapter.py`. Version is pinned in the worker Dockerfile.

2. **Derived vs Contributed knowledge — never conflate.**
   - *Derived* = Graphify output (`graph.json`, Markdown). Rebuildable, overwritable, versioned on the volume.
   - *Contributed* = human/agent annotations & comments (Fase 3). Must persist across rebuilds → Postgres, overlaid at query time.
   - Contributed knowledge is NEVER written into `graph.json`. Violating this loses knowledge on every rebuild.

3. **No full-graph endpoint.** No MCP tool ever returns the whole `graph.json`. Every
   result is size-capped server-side. Scoped query > full dump — that is the whole point.

4. **Agents reach only the MCP server.** No agent path touches the docs app (Fase 2) or
   writes to `graph.json`.

5. **One writer per project for builds.** Builds go to a staging dir, get validated, then
   promote atomically (symlink flip). Agents must never see a half-built graph.

## Stack

- Python. Package/venv via **uv**.
- MCP server: **FastMCP**.
- Graph store: **NetworkX** in-memory + **SQLite FTS** (ephemeral read index).
- Metadata DB: **Postgres** via **psycopg3** + plain SQL migrations in `db/migrations/*.sql`.
  No ORM, no Alembic, no goose. Hand-write migrations.
- Deploy: docker-compose.

## Layout

```
common/   shared package: config, db, schema types (imported by worker + mcp)
worker/   registry, graphify_adapter, build, promote, webhook
mcp/      server, graphstore, tools, auth, search
db/migrations/*.sql
data/     gitignored volume (versioned graph output)
tests/fixtures/graphify-out/   sample graph for tests
```

## Conventions

- Tests: **pytest, TDD** — write the failing test first. Fixtures use a real sample
  `graphify-out/` dir, not hand-faked JSON where avoidable.
- Every MCP tool enforces its hard size cap regardless of caller input.
- Secrets (deploy keys, webhook secrets) are referenced from `projects.yaml`, never inlined;
  encrypted at rest on the worker.
- `cost.json` from Graphify is never committed and never served.
- Follow the module boundaries in the spec: consumers use `graphstore` query fns and
  `graphify_adapter` functions — never parse `graph.json` directly elsewhere.

## Phases

Fase 1 (current): worker + MCP + Postgres, read-only. No docs app, no annotations.
Fase 2: Fumadocs docs app. Fase 3: contributed knowledge + comment→agent→PR loop.
Fase 4: nice-to-haves. Do not build later-phase features early.
