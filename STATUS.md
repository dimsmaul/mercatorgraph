# Project Status

Where the platform stands: what's built, what's next, what needs hardening.
Last updated: 2026-07-29.

## Position

**Fase 1 (MVP, read-only) and Fase 2 (docs app) are implemented and tested.**
74 automated tests green; all three service images build; MCP hot path and docs app proven
end-to-end. Not yet: contributed knowledge (Fase 3), Fase 4 extras, and several production
hardening items below.

---

## ✅ Provided

### Fase 1 — Centralized read-only

| Area | Feature |
|------|---------|
| Common | Typed node-link schema (3 confidence tags), `projects.yaml` config + secret refs, psycopg3 pool, SQL migration runner |
| DB | `projects`, `builds`, `tokens`, `audit_log`, `annotations` (Fase 3 stub) |
| Worker | `graphify update` headless build (+ fixture mode), per-project lock, clone/pull, staging, validation (node>0, drop-ratio guard, `force`), **atomic promote** (symlink flip) + retention N=5 |
| Worker API | `POST /webhook/{slug}` (HMAC verify), `POST /projects/{slug}/rebuild`, `GET /projects/{slug}/status`, `GET /projects/{slug}/graph.html`, `GET /health` |
| MCP | graphstore (networkx DiGraph + degree + cached betweenness + SQLite FTS), hot-reload registry |
| MCP tools | `list_projects`, `query_graph` (deterministic), `get_node`, `trace_path`, `blast_radius`, `search` (cross-project, scoped) — all size-capped |
| MCP auth | DB-backed bearer `TokenVerifier`, per-project scope check, audit log |
| Deploy | docker-compose (postgres + worker + mcp), graphify `0.9.28` pinned |

### Fase 2 — Docs app

| Area | Feature |
|------|---------|
| Generator (`ckdocs`) | `graph.json` + `GRAPH_REPORT.md` → MDX: index (report embed + graph embed), per-community pages, per-node pages (in/out edges + confidence), frontmatter (project/cluster/tags/confidence/graph_version), `versions.json`, MDX-escaping, idempotent, multi-project |
| Docs app | Fumadocs (Next 16 / Tailwind 4, bun): per-project grouping, per-node & per-community pages, stable permalinks |
| Docs features | Cross-project **Orama search** (`/api/search`), **staleness badge** (page vs latest build), **subgraph embed** (iframe graphify `graph.html`) |
| Deploy | docs Dockerfile (standalone) + compose `docs` service |

### Publishing

| Area | Feature |
|------|---------|
| Images | `image:` tags on all services (`${IMAGE_PREFIX}/…:${TAG}`), pull-only `docker-compose.deploy.yml`, `Makefile` (build / push / multi-arch buildx) |
| Runtime config | docs worker URL resolved at runtime via `/api/config` (`WORKER_URL` env) — no build-time bake; worker **CORS** middleware for docs-origin browser calls |
| Clean-build safe | committed landing page so a fresh-checkout docs image is never empty |

---

## 🔜 Needed (not yet built)

### Fase 3 — Contributed knowledge & feedback loop

- [x] **Knowledge persists across rebuild (G3)** — annotations in Postgres, keyed by
      `(project, node_id)`, untouched by graph rebuild; proven by test.
- [x] MCP tool **`add_annotation`** (scoped, audited, node-checked); annotations surfaced in
      `get_node` (full) + `query_graph` (count) with a **`CONTRIBUTED`** tag — overlay at
      query time, never written into `graph.json`.  *(SP1)*
- [x] Inline **block-level comments** (anchored to node) → Postgres — worker API
      (`POST/GET/PATCH /projects/{slug}/comments`). Docs UI widget deferred.  *(SP2 backend)*
- [x] Thread status: `open` / `addressed-by-agent` / `resolved` (validated transitions).  *(SP2)*
- [ ] Comment → webhook → agent job → **open a PR** (never direct write)  *(SP3)*
- [ ] Diff view before/after agent revision + developer approval  *(SP3)*

### Fase 4 — Nice to have

- [x] **Graph diff** between two versions — `graph_diff` MCP tool (added/removed nodes+edges,
      defaults to last two versions, scoped, capped).  *(SP5)*
- [ ] Graph diff by git **commit** (not just build version)
- [x] **Staleness notifications** — best-effort `Notifier` posts a `build.succeeded` event to
      `NOTIFY_URL` on promote (Slack-compatible).  *(SP6)*
- [x] **Build & usage stats** — `/stats/builds` (per-project status counts) + `/stats/usage`
      (tool call counts from audit_log). JSON API; UI page deferred.  *(SP7)*

---

## ⚠️ Gaps to harden (before "production-real")

These are inside already-shipped phases — small but real.

- [x] ~~CORS on worker~~ — added `CORSMiddleware` (`WORKER_CORS_ORIGINS`), tested.
- [x] ~~Runtime worker URL~~ — docs now read `WORKER_URL` at runtime via `/api/config`;
      verified in a clean image (`/api/config` reflects the container env).
- [x] ~~Empty docs image on clean checkout~~ — committed landing page; clean build serves `/docs`.
- [x] **Auto-regen docs on promote** — worker regenerates the MDX via `ckdocs` into
      `DOCS_CONTENT_DIR` after each promote (best-effort). A docs *rebuild* to serve new
      content is still separate under pipeline A.
- [ ] **Live browser e2e** of `StaleBadge` / `GraphEmbed` against a running worker (code
      path + CORS + `/api/config` proven; full browser round-trip not yet exercised).
- [ ] **Full 4-service `docker compose up`** validated together (Fase 1 stack + docs proven
      separately, not in one run).
- [ ] **Repo credentials** — `projects.yaml` references a secret env var, but encrypted
      deploy-key storage / private-repo clone is not implemented (only public/HTTPS today).
- [ ] **Token expiry / revocation** — `tokens` has no expiry; no rotation or rate limiting.
- [x] ~~Webhook debounce~~ — per-project trailing debounce coalesces push bursts
      (`DEBOUNCE_SECONDS`, off by default); tested.
- [x] ~~cron trigger~~ — interval-based `CronScheduler` per project (`rebuild_interval`),
      started on worker startup; reuses the build lock/validate/promote path.
- [ ] **Betweenness perf** on large graphs — exact computation may be slow; may need a
      k-sample approximation.
- [ ] **`query_graph` is deterministic** (FTS seed + BFS) — no LLM semantic ranking yet.
- [ ] **MCP host-port** — `8080` conflicts with a local `server` process on this machine;
      remap in `docker-compose.yml` for host access.
- [ ] **worker HTTP endpoints unauthenticated** (`/status`, `/stats/*`, `/rebuild`,
      `/graph.html`) — internal/network-protected by design; add token auth + redact raw build
      `error` strings if ever exposed. (Security-review flag.)

---

## Test coverage snapshot

- `common/` schema, config, db + migrations
- `mcp/` graphstore, auth, tools, server + registry hot-reload
- `worker/` graphify adapter, build/promote pipeline, FastAPI (webhook/HMAC/status/graph.html)
- `docs-gen/` generator (files, frontmatter, permalinks, MDX-escape, idempotency, multi-project)

Run: `DATABASE_URL=… uv run pytest` (DB-dependent tests skip without `DATABASE_URL`).
