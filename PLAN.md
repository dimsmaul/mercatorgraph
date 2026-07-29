# PLAN — Fase 1: MCP server + FastAPI worker

Implementation plan for Fase 1. Source of truth for scope:
`docs/superpowers/specs/2026-07-28-fase1-mvp-design.md`. Conventions: `CLAUDE.md`.
Architecture: `flow.md`.

## Context

Repo starts with design docs only — zero code. This plan builds the two Fase 1 Python
HTTP services and their shared foundation:

- **mcp** — FastMCP server exposing 6 read-only, size-capped graph tools to agents.
- **worker (FastAPI)** — HTTP layer: git-push webhook (primary trigger), manual rebuild,
  build status; drives clone/pull → graphify build → validate → atomic promote.
- **common** — shared package (schema types, config, db) imported by both.
- **db** — Postgres schema via psycopg3 + plain SQL migrations.

"mcp" and "fast api" map to the `mcp` service (FastMCP) and the `worker` service (FastAPI).
Separate containers, separate processes.

Goal: `docker compose up` indexes a project's graph and serves it to agents, meeting PRD
exit criteria (≥2 projects, ≥3 agents, p95 < 300 ms).

## Open dependency (spike, step 0)

Graphify's `/graphify .` is a **skill invocation through an AI assistant**, not a pure CLI
build. The non-interactive command that emits a `--code-only` `graph.json` in CI must be
confirmed against the pinned `graphifyy` version. Until confirmed, `graphify_adapter` runs
in **fixture/replay mode** (loads a committed sample `graph.json`) so mcp + worker are fully
buildable and testable now. Real invocation is isolated to one function.

## Approach

TDD (pytest, failing test first). Build bottom-up so each layer is testable against the
layer below with a committed `graphify-out/` fixture — MCP does not wait on the worker.

Stack per `CLAUDE.md`: Python + uv, FastMCP, NetworkX + SQLite FTS, psycopg3 + SQL
migrations (no ORM). `graphify_adapter` and `graphstore` are the only modules that touch
`graph.json`.

## Steps

**0. Spike — confirm graphify headless build.** Install pinned `graphifyy`; find the
non-interactive `--code-only` build command. Record in spec §2.1. Fallback: fixture mode
behind a feature flag.

**1. Repo scaffold.** uv packages `common/`, `worker/`, `mcp/` (each `pyproject.toml`);
`docker-compose.yml`; `.gitignore` (`data/`, `cost.json`, `.env`); `.env.example`;
`projects.yaml` sample; `tests/fixtures/graphify-out/graph.json` (sample with all 3
confidence tags).

**2. `common/schema.py`.** Typed `GraphNode`, `GraphEdge`, layout constants, confidence
enum `EXTRACTED|INFERRED|AMBIGUOUS`. Tests parse fixture, tolerate missing optionals.

**3. `common/config.py`.** Load `projects.yaml` + resolve secrets from env/file. Tests.

**4. `common/db.py` + `db/migrations/001_init.sql`.** psycopg3 pool + helpers; tables
`projects`, `builds`, `tokens`, `audit_log`, `annotations` (stub, unused); migration runner.
Tests against a test DB.

**5. `mcp/graphstore.py` (core).** Load `graph.json` via
`nx.node_link_graph(data, edges="links")` (graphify emits standard node-link JSON) →
`DiGraph`; compute degree + cached betweenness; SQLite FTS over label+source_file+report.
Scoped fns: `neighborhood`, `node_detail`, `paths` (`nx.shortest_path`),
`blast_radius` (`nx.ancestors`/reverse ego within depth), `search`. Consumers never see raw
json. TDD against fixture. **Decision C:** extraction delegated to graphify (`update`);
query traversal done in-process with networkx on graphify's own format — no CLI text parsing.

**6. `mcp/auth.py`.** Token hash lookup → principal + scopes; `check_scope`; `audit`.
Tests: scope denial, cross-project filter, invalid token rejected + audited.

**7. `mcp/tools.py`.** 6 tools with server-side hard caps (max_nodes 100, search limit 50,
depth 4). `query_graph` = FTS seed → capped BFS neighborhood → deterministic summary (no
LLM). TDD contract tests.

**8. `mcp/server.py`.** FastMCP wiring; bearer middleware; hot-reload watcher on `current`
symlink (build new store, atomic ref swap); uvicorn entrypoint; HTTP/streamable transport.

**9. `worker/graphify_adapter.py`.** `load_graph_json` + `run_build` = `graphify update
<repo_dir>` (headless, no LLM; `--force` guard) + fixture mode. Sole owner of graphify
knowledge; version pinned in Dockerfile (0.9.28). Tests.

**10. `worker/registry.py` + `build.py` + `promote.py`.** registry resolves project →
repo/creds; build does lock → clone/pull → staging → validate; promote does atomic symlink
flip + retention prune (N=5). Tests with mocked adapter: atomicity, validate-abort keeps
current, lock serializes.

**11. `worker/webhook.py` (FastAPI).** `GET /health`, `POST /webhook/{slug}` (HMAC verify
→ enqueue), `POST /projects/{slug}/rebuild`, `GET /projects/{slug}/status`. Tests: bad sig
rejected, valid triggers build, status returns record.

**12. Containerization.** `worker/Dockerfile` (pinned `graphifyy` + git), `mcp/Dockerfile`;
wire `docker-compose.yml` with shared `/data` volume + postgres.

## Files (representative)

```
docker-compose.yml  .gitignore  .env.example  projects.yaml
common/pyproject.toml  common/src/common/{schema,config,db}.py
mcp/pyproject.toml     mcp/src/mcp/{graphstore,auth,tools,server}.py  mcp/Dockerfile
worker/pyproject.toml  worker/src/worker/{graphify_adapter,registry,build,promote,webhook}.py  worker/Dockerfile
db/migrations/001_init.sql
tests/fixtures/graphify-out/graph.json
```

## Verification (end-to-end)

1. `pytest` green in `common/`, `mcp/`, `worker/`.
2. `docker compose up` → postgres migrated, worker + mcp healthy (`GET /health`).
3. Seed `projects.yaml` + insert a scoped token.
4. `POST /projects/<slug>/rebuild` → `GET /status` = `succeeded`, `current` symlink points
   at a version dir.
5. MCP client with bearer token → all 6 tools return bounded results.
6. Scope: token for project A denied on B; `audit_log` rows written.
7. `query_graph` p95 < 300 ms on the sample graph.

## Out of scope (later phases)

Fumadocs docs app (Fase 2); annotations / `add_annotation` / comment→agent→PR (Fase 3);
LLM semantic `query_graph`; admin UI; graph diff + dashboards (Fase 4).
