# Mercatorgraph

Self-hosted platform that turns [Graphify](https://github.com/Graphify-Labs/graphify)
into **one centralized knowledge graph per project**, served to many AI agents (via MCP)
and many developers (via a docs app).

Graphify is treated as a **dependency, not a fork** — we consume its `graphify-out/` output
(`graphify update` for headless builds) and never touch its internals.

> Design: [`PRD.md`](PRD.md) · plan: [`PLAN.md`](PLAN.md) · architecture &
> data flow: [`FLOW.md`](FLOW.md) · specs: [`docs/superpowers/specs/`](docs/superpowers/specs/)

## Architecture

```
Agent     ──► MCP server ──► graphstore (in-memory)   hot path, read-only, scoped
Developer ──► Docs app   ──► generated MDX             browse / search / staleness
Git push  ──► Worker     ──► volume + Postgres         build, validate, atomic promote
```

| Service | Stack | Role |
|---------|-------|------|
| **worker** | Python · FastAPI | clone/pull → `graphify update` → validate → atomic promote; webhook + manual rebuild + status + `graph.html` |
| **mcp** | Python · FastMCP | load `graph.json` (networkx + SQLite FTS), 6 size-capped tools, bearer auth + project scope + audit |
| **docs** | Next.js · Fumadocs (bun) | per-project/community/node pages, cross-project search, staleness badge, subgraph embed |
| **postgres** | — | durable metadata: projects, builds, tokens, audit_log (annotations stub for Fase 3) |
| **ckdocs** | Python | generator: `graph.json` + `GRAPH_REPORT.md` → Fumadocs MDX tree |

**Derived vs contributed:** graph output is rebuildable (volume, versioned). Human/agent
knowledge (Fase 3) is durable (Postgres, overlaid at query) — never written into `graph.json`.

## Quickstart (Docker)

> Running from **published images**? See [`example/`](example/) — a full guide (install,
> quickstart, config/volumes, the worker/mcp/docs split, production) with a ready-to-run
> `docker-compose.yml`.

Building from source:

```bash
cp .env.example .env          # set POSTGRES_PASSWORD etc.
docker compose up -d --build  # postgres + worker + mcp + docs
```

Register a project in `projects.yaml`, then build and query:

```bash
# 1. build the graph for a project
curl -X POST localhost:8000/projects/demo/rebuild
curl localhost:8000/projects/demo/status         # wait for "succeeded"

# 2. mint a scoped bearer token for an agent
TOKEN=my-agent-token
HASH=$(python3 -c "import hashlib,sys;print(hashlib.sha256('$TOKEN'.encode()).hexdigest())")
docker compose exec -T postgres psql -U knowledge -d knowledge -c \
  "INSERT INTO tokens (token_hash, principal, scopes) VALUES ('$HASH','my-agent', ARRAY['demo']);"
```

**Connect Claude Code** (or any MCP client) to the MCP server:

```bash
claude mcp add codegraph --transport http http://localhost:8080/mcp \
  --header "Authorization: Bearer my-agent-token"
```

Tools: `list_projects`, `query_graph`, `get_node`, `trace_path`, `blast_radius`, `search`.

**Docs app:** http://localhost:3000/docs (humans only — agents use MCP).

> Ports 8000 (worker) · 8080 (mcp) · 3000 (docs). If 8080 is taken, remap the `mcp` port in
> `docker-compose.yml`.

## Development

Python workspace uses [uv](https://docs.astral.sh/uv/); docs app uses
[bun](https://bun.sh/).

```bash
uv sync --python 3.12                              # install all packages
uv run pytest                                      # runs; DB tests skip without DATABASE_URL

# with a throwaway Postgres for DB/auth/tool/webhook tests:
docker run -d --name pg -e POSTGRES_PASSWORD=test -e POSTGRES_USER=test \
  -e POSTGRES_DB=test -p 55432:5432 postgres:17-alpine
DATABASE_URL=postgresql://test:test@localhost:55432/test uv run pytest

# docs app
cd docs && bun install && bun run build            # or: bun run dev
```

Regenerate docs content from a built graph:

```bash
uv run python -c "from ckdocs import generate_project; \
  generate_project('data/projects/demo/current/graphify-out','demo','<version>','docs/content/docs')"
```

## Layout

```
common/    ckcommon: schema, config, db + migrations
mcp/       ckmcp: graphstore, auth, tools, registry, server
worker/    ckworker: graphify_adapter, build, promote, registry, webhook
docs-gen/  ckdocs: MDX content generator
docs/      Fumadocs Next app (bun)
db/migrations/*.sql
tests/fixtures/graphify-out/   sample graph for tests
data/      gitignored volume (versioned graph output)
```

## Status

- **Fase 1 — MVP (read-only):** ✅ worker + MCP + Postgres, atomic builds, scoped tools.
- **Fase 2 — Docs app:** ✅ Fumadocs, per-node pages, cross-project search, staleness, embed.
- **Fase 3 — Contributed knowledge:** planned — inline comments, `add_annotation`,
  comment → agent → PR loop.
- **Fase 4:** graph diff between releases, staleness notifications, dashboards.
