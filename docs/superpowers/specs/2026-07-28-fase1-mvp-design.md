# Fase 1 MVP — Design Spec

**Project:** Centralized Codebase Knowledge Platform (Graphify-based)
**Phase:** Fase 1 — Centralized Read-Only (Python only)
**Date:** 2026-07-28
**Status:** Approved for planning
**Source PRD:** `PRD.md`

---

## 1. Goal & Scope

Deliver a self-hosted, centralized, **read-only** knowledge-graph service: one graph per project, built by wrapping the Graphify CLI, served to many AI agents through a single MCP interface.

**In scope (Fase 1):**
- Worker: clone/pull repos, run Graphify headless, version output, atomic promote.
- MCP server: load active graph into memory, serve 6 scoped tools, token auth + audit.
- Postgres: durable metadata (projects, builds, tokens, audit log).
- One `docker-compose` bringing up worker + mcp + postgres + shared volume.

**Out of scope (Fase 1):**
- Fumadocs / docs app (Fase 2).
- Contributed knowledge: annotations, comments, `add_annotation` tool (Fase 3).
- LLM-backed semantic query inside MCP. Fase 1 `query_graph` is deterministic.
- Admin UI. Projects are registered via a config file.
- Any agent writing to `graph.json`.

**Exit criteria (from PRD):** ≥2 projects indexed, ≥3 distinct agents query successfully, p95 MCP query latency < 300 ms.

---

## 2. Grounded Graphify Contract

Verified against `github.com/Graphify-Labs/graphify` on 2026-07-28. **This is the most expensive interface to change; the `graphify_adapter` module is its sole owner.**

**Install:** `uv tool install graphifyy` (package `graphifyy`, command `graphify`). Verified
version at grounding: **0.9.28**. Ships **two** executables: `graphify` (CLI) and
`graphify-mcp` (`python -m graphify.serve`, an MCP server over stdio/HTTP).

**Headless build (spike §2.1 RESOLVED):** `graphify update <path>` re-extracts code files and
writes `graph.json` with **no LLM, no skill, no API key** — works on first build too. This is
the worker's build command. `--force` overrides the fewer-nodes guard.

**CLI query primitives** (operate on a `graph.json`, headless): `graphify query "<q>" --budget N`,
`graphify path "A" "B"`, `graphify explain "X"`, `graphify affected "X" --depth N`,
`graphify god-nodes --top N`. These map closely to our MCP tools.

**graphify-mcp** serves one `graph.json`: `graphify-mcp --transport http --host --port
--api-key --path /mcp --stateless`. Single graph, single api-key, no multi-project scoping,
no audit, no Postgres overlay.

**Output dir `graphify-out/`:**
| File | Meaning |
|------|---------|
| `graph.json` | full queryable graph (the artifact we consume) |
| `GRAPH_REPORT.md` | key concepts + suggested questions (indexed for FTS) |
| `graph.html` | interactive viz (developers open this in Fase 1; we don't parse it) |
| `cache/` | incremental-update cache |
| `cost.json` | API usage — **never commit, never serve** |
| `<project>-callflow.html` | architecture diagram (ignored in Fase 1) |

**`graph.json` = NetworkX node-link JSON** (verified on 0.9.28). Top level:
`{ directed, multigraph, graph, nodes, links, hyperedges }`. Edges live under **`links`**, not
`edges`. Loads directly with `networkx.node_link_graph(data, edges="links")` — no manual parse.

**Node (real fields):** `{ id, label, file_type (code|doc|pdf|...), source_file,
source_location ("L1" string), community, community_name, norm_label, _origin }`.
- `community` = cluster id; `community_name` = human label.
- **No `degree`, no `line`** as the earlier idealized schema claimed. `source_location` is a
  string like `"L1"`. Degree and betweenness centrality are computed in `graphstore` via NetworkX.

**Edge / link (real fields):** `{ source, target, relation (contains|calls|imports|...),
confidence (EXTRACTED|INFERRED|AMBIGUOUS), confidence_score (float), weight, source_file,
source_location, _origin }`.
- Three confidence tags confirmed. Adapter preserves all. Fase 3 adds `CONTRIBUTED` at the
  overlay layer, never inside `graph.json`.
- `hyperedges` key exists at top level — ignored in Fase 1 (revisit if multi-endpoint edges matter).

**Build flags used:** `--code-only` (tree-sitter only, zero LLM cost, no API key), `--update` (incremental, changed files only), `--force` (override node-count guard).

### 2.1 OPEN RISK — headless build entrypoint

`/graphify .` in the docs is a **skill invocation** that runs *through* an AI assistant, not a pure CLI build. The documented headless/CI path is `graphify extract` (+ `--backend`), which targets docs/LLM extraction. The exact non-interactive command that produces a `--code-only` `graph.json` in CI **must be verified against the pinned Graphify version during implementation** (spike task #0 in the plan). Mitigation: pin the version in the worker Dockerfile; keep all invocation logic inside `graphify_adapter` so a command change touches one file.

---

## 3. Architecture

```
┌─ docker-compose ─────────────────────────────────────────┐
│                                                          │
│  worker (Python)                                         │
│   registry → clone/pull → graphify build (staging)       │
│   → validate → atomic promote → notify mcp               │
│   trigger: push webhook (primary) | manual endpoint      │
│                                                          │
│  mcp (Python + FastMCP)   ← HOT PATH                     │
│   graphstore: graph.json → NetworkX + SQLite FTS         │
│   6 tools, bearer token, project scope, audit            │
│                                                          │
│  postgres: projects, builds, tokens, audit_log          │
│  volume /data: projects/<slug>/versions/<ts>/ + current  │
└──────────────────────────────────────────────────────────┘

Agent ──► mcp ──► graphstore (in-memory)   [hot path, <300ms p95]
Push  ──► worker ──► volume + postgres      [heavy, rare, locked]
```

**Hard rule (PRD §5):** agents only ever reach the MCP server. No agent path touches the (future) docs app, and no tool returns the full `graph.json`.

---

## 4. Data Flow

### 4.1 Build path (heavy, rare, one writer per project)

1. Push webhook received → verify HMAC signature against project's `webhook_secret`.
2. Enqueue build job; acquire **per-project lock** (reject/queue concurrent builds for same project).
3. Clone (first build) or pull (subsequent) using read-only deploy key.
4. Run graphify into a **staging** version dir: `data/projects/<slug>/versions/<ts>/graphify-out/`.
   - `--code-only --update` by default (per-project overridable in `projects.yaml`).
5. **Validate** staging: `graph.json` parses, `node_count > 0`, no large unexplained node-count drop vs current (guard against corrupt/partial build; `--force` in config bypasses).
6. **Atomic promote:** flip the `current` symlink to the new version dir (single rename = atomic).
7. Notify mcp to hot-reload (or mcp detects version change); write a `builds` row (`succeeded`).
8. Prune versions beyond retention (default N=5).

Failure at any step → current live graph untouched, `builds` row = `failed` with error, no promote.

### 4.2 Query path (light, concurrent, read-only)

1. Agent calls an MCP tool with a bearer token.
2. Auth middleware: hash-lookup token → resolve principal + scopes; reject if invalid (401-equivalent).
3. Scope check: requested `project` must be in scopes (or scope `*`). Cross-project `search` intersects results with allowed scopes.
4. Tool executes against in-memory graphstore; **result is size-capped**.
5. Append `audit_log` row (principal, tool, project, args summary, ts).

### 4.3 Graph hot-reload

mcp holds the active graphstore behind a single reference. On reload it builds a **new** graphstore from the promoted version, then atomically swaps the reference. In-flight reads finish on the old store. Agents never observe a half-built graph.

---

## 5. Module Boundaries

Each unit: one purpose, well-defined interface, independently testable.

| Module | Purpose | Depends on | Consumers see |
|--------|---------|-----------|---------------|
| `common/schema` | typed models for graph nodes/edges + graphify-out layout constants | — | types only |
| `common/config` | load `projects.yaml`, env secrets | — | config objects |
| `common/db` | postgres connection + query helpers (psycopg3) | postgres | typed rows |
| `worker/graphify_adapter` | **sole owner** of graphify invocation + graph.json parsing | graphify CLI, common/schema | `run_build()`, `load_graph_json()` |
| `worker/registry` | resolve project → repo url/branch/creds | common/config | project records |
| `worker/build` | orchestrate: lock, clone/pull, staging, validate | adapter, registry | `build_project(slug)` |
| `worker/promote` | atomic symlink flip + retention prune | — | `promote(slug, version)` |
| `worker/webhook` | verify signature, enqueue, manual endpoint | build | HTTP routes |
| `mcp/graphstore` | graph.json → NetworkX DiGraph + SQLite FTS; cached betweenness; scoped query fns | common/schema | query fns only (never raw json) |
| `mcp/search` | FTS index build + query over label/source_file/report | graphstore | `search()` |
| `mcp/auth` | token hash lookup, scope check, audit write | common/db | middleware + `check_scope()` |
| `mcp/tools` | 6 MCP tools, thin, size-cap enforcement | graphstore, auth | FastMCP tools |
| `mcp/server` | FastMCP app wiring, reload trigger | all mcp/* | entrypoint |

The `graphify_adapter` and `graphstore` boundary is the core isolation: consumers never read `graph.json` directly, so a Graphify format change or a store swap (NetworkX → SQLite) touches one module.

---

## 6. MCP Tool Contract (Fase 1)

Every tool returns a **size-bounded** result. No endpoint returns the whole graph.

| Tool | Input | Output | Fase 1 impl |
|------|-------|--------|-------------|
| `list_projects` | — | `[{slug, last_build, node_count, edge_count}]` | read `builds` + `projects` |
| `query_graph` | `project`, `question`, `max_nodes?` | subgraph + deterministic summary | FTS seed match → depth-limited BFS neighborhood capped at `max_nodes` (default 30) → summary = top nodes by degree/centrality + their edge explanations. **No LLM.** |
| `get_node` | `project`, `node_id` | node detail + direct edges | direct NetworkX lookup; annotations slot empty (Fase 3) |
| `trace_path` | `project`, `from`, `to`, `max_paths?` | path(s) + per-edge explanation | NetworkX shortest path(s); each edge carries relation + confidence + explanation |
| `blast_radius` | `project`, `node_id`, `depth?` | impacted nodes ranked | reverse-reachability within `depth`, ranked by cached betweenness centrality |
| `search` | `project?`, `query`, `limit?` | FTS hits (node + report) | SQLite FTS; `project` omitted = cross-project, intersected with token scopes |

`add_annotation` is **Fase 3**, not implemented here.

Every returned edge preserves its `EXTRACTED|INFERRED|AMBIGUOUS` tag.

**Size caps:** `max_nodes` default 30 / hard max 100; `search.limit` default 20 / hard max 50; `blast_radius.depth` default 2 / hard max 4. Caps are enforced server-side regardless of caller input.

---

## 7. Storage & Persistence

**Derived (rebuildable, overwritable):** `graph.json` + Markdown, versioned on the shared volume under `data/projects/<slug>/versions/<ts>/`. `current` symlink points at the live version. Retention N=5 (configurable).

**Metadata (durable, Postgres):**
- `projects(slug PK, repo_url, branch, build_flags, webhook_secret_ref, created_at)`
- `builds(id PK, project_slug FK, version_ts, status, node_count, edge_count, error, started_at, finished_at)`
- `tokens(id PK, token_hash, principal, scopes text[], created_at, last_used_at)`
- `audit_log(id PK, principal, tool, project_slug, args_summary, created_at)`
- `annotations(...)` — **table created but unused in Fase 1**, reserved for Fase 3 (keeps the derived-vs-contributed split visible from day one).

Postgres holds durable metadata; SQLite FTS is an ephemeral read index rebuilt per graph load. Two stores, on purpose (PRD §7).

---

## 8. Auth & Multi-tenancy

- Token per user and per agent; stored hashed. Bearer on every MCP call.
- `scopes` = list of project slugs, or `*` for all.
- Every tool checks scope; cross-project `search` is intersected with the caller's scopes (**resolves PRD open-Q2: scoped by token, not blanket all-see-all**).
- `audit_log` records who queried what, when.
- Repo credentials: read-only deploy keys, encrypted at rest on the worker, referenced (not inlined) from `projects.yaml`.

---

## 9. Error Handling

| Case | Behavior |
|------|----------|
| Build fails (clone/graphify error) | current graph untouched; `builds.status=failed` + error; no promote |
| Validation fails (unparseable / node_count=0 / big drop) | abort promote; keep current; log |
| Invalid/expired token | reject, no data leak, audit the attempt |
| Unknown project / node | structured not-found error |
| Oversized request | server clamps to hard-max cap, never dumps full graph |
| Concurrent build same project | lock → queue or reject second (config) |

---

## 10. Testing Strategy (TDD, pytest)

- **graphify_adapter:** fixture `graphify-out/` dir → parse → assert nodes/edges, all three confidence tags, missing-field tolerance.
- **graphstore:** small known graph → assert `blast_radius`, `trace_path`, `query_graph` neighborhood, betweenness ranking, size-cap enforcement.
- **build orchestrator:** mocked graphify run → assert staging→validate→promote atomicity, lock behavior, validate-abort keeps current.
- **auth/scope:** token scoped to `[a]` cannot read project `b`; cross-project search filtered to scopes; invalid token rejected + audited.
- **tools contract:** each tool returns declared shape and respects hard caps.
- Fixtures: at least one sample `graphify-out/` committed under `tests/fixtures/`.

---

## 11. Stack Decisions

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Language | Python | native to Graphify + NetworkX |
| MCP framework | FastMCP | PRD choice; single-language graph libs |
| Graph store | NetworkX in-memory + SQLite FTS | ms queries; read-only fan-out is cheap |
| Metadata DB | Postgres via **psycopg3 + plain SQL migrations** (`db/migrations/*.sql`) | few tables; light; hand-written migrations preferred over ORM/Alembic for this size |
| Shared code | `common/` package imported by worker + mcp | schema types, config, db in one place |
| Deploy | docker-compose | self-hosted, per-service images |
| Graphify version | pinned in worker Dockerfile | insulate against fast releases (PRD risk #1) |

---

## 12. Repo Layout

```
docker-compose.yml
CLAUDE.md            # repo conventions
flow.md              # architecture + sequence diagrams
PRD.md
projects.yaml        # registered repos (secrets referenced, not inlined)
common/
  pyproject.toml
  src/common/{config,db,schema}.py
worker/
  Dockerfile  pyproject.toml
  src/worker/{registry,graphify_adapter,build,promote,webhook}.py
  tests/
mcp/
  Dockerfile  pyproject.toml
  src/mcp/{server,graphstore,tools,auth,search}.py
  tests/
db/migrations/*.sql
data/                # gitignored volume mount
tests/fixtures/graphify-out/   # sample graph for tests
```

---

## 13. Resolved Open Questions (PRD §12)

| PRD Q | Resolution (Fase 1) |
|-------|---------------------|
| Q1 rebuild per-commit vs debounce | Webhook-triggered; per-project lock serializes. Debounce deferred (only needed under high push frequency; add later if measured). |
| Q2 cross-project search visibility | Scoped by token; `search` results intersected with caller scopes. |
| Q3 agent annotation approval | N/A in Fase 1 (annotations are Fase 3). |
| Q4 snapshot retention | Keep N=5 versions, configurable. |

---

## 14. Deferred to Later Phases

- **Fase 2:** Fumadocs docs app, MD ingestion, staleness indicators, subgraph embeds.
- **Fase 3:** contributed knowledge — inline comments, `add_annotation`, `CONTRIBUTED` overlay at query time, comment→agent→PR loop.
- **Fase 4:** graph diff between releases, staleness notifications, build/usage dashboard.
- **Semantic `query_graph`** (LLM-ranked) — potential enhancement once deterministic version is validated.
