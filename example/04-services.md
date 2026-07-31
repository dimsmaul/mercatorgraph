# 04 — The services, and why they're separate

Mercatorgraph is split into three app services plus Postgres. The split is deliberate — each
has a different job, a different consumer, and a different performance profile.

```
                    ┌──────────────┐
   git push ───────►│    worker    │  builds the graph (heavy, rare)
   cron / manual    │  (FastAPI)   │
                    └──────┬───────┘
                           │ writes versioned graph + atomic promote
                           ▼
                    ┌──────────────┐        ┌──────────────┐
                    │  /data volume │◄──────│     mcp      │  serves agents (fast, read-only)
                    │ (shared)      │  reads │  (FastMCP)   │◄──── AI agents (bearer token)
                    └──────────────┘        └──────────────┘
                           ▲
                    ┌──────┴───────┐
                    │      view      │  graph viewer (optional)
                    │  (Next.js)   │◄──── developers (browser)
                    └──────────────┘

           ┌──────────────┐
           │   postgres   │  durable metadata (projects, builds, tokens, audit, comments)
           └──────────────┘  used by worker + mcp
```

## worker — the builder (write path)

- **Does:** clones/pulls a repo, runs `graphify update` to extract the graph, validates the
  result (parses, non-empty, no suspicious node-count drop), then **promotes** it by flipping
  the `current` symlink atomically. Prunes old versions. Records each build in Postgres.
- **Triggered by:** git-push webhook (primary), cron interval, or a manual `rebuild` call.
- **Talks to:** the `/data` volume (writes) and Postgres (build rows).
- **Why separate:** building is **heavy and infrequent**, and needs git + the Graphify engine
  in its image. You don't want that weight in the hot query path, and you want exactly **one
  writer per project** (a lock) so agents never see a half-built graph.

## mcp — the query server (read path, the hot path)

- **Does:** loads the current `graph.json` into memory (NetworkX + a SQLite full-text index),
  computes centrality once, and serves **scoped, size-capped** tools: `query_graph`,
  `get_node`, `trace_path`, `blast_radius`, `search`, `list_projects`, `add_annotation`,
  `graph_diff`. Every call is bearer-token authed, checked against the caller's project
  scopes, and audited.
- **Talks to:** the `/data` volume (reads only) and Postgres (tokens, audit, annotations).
- **Why separate:** this is the **latency-sensitive** path (target p95 < 300 ms). Many agents
  read concurrently — cheap because it's read-only and in-memory. Keeping it apart from the
  builder means a rebuild never slows down or blocks queries. When the worker promotes a new
  version, the mcp server hot-swaps to it without dropping in-flight reads.
- **Hard rule:** no tool ever returns the whole graph — scoped answers only.

## view — the human UI (graph viewer) (optional)

- **Does:** renders the graph as browsable pages — a page per project, per community
  (cluster), and per node (with its edges), plus cross-project search, a staleness badge, and
  an interactive subgraph embed.
- **Talks to:** generated MDX content (built at image build time) and, from the browser, the
  worker's `/status` + `/graph.html` at runtime.
- **Why separate:** it's a **React/Next.js** app — a different language and a low-stakes
  concern that must never affect agent performance. Humans use it; agents never do. You can
  skip this service entirely and still have a fully working agent platform.

## postgres — durable metadata

Holds everything that must survive a graph rebuild: `projects`, `builds`, `tokens`,
`audit_log`, and `annotations` (contributed knowledge — annotations + comments with thread
status). The graph itself is *not* here; it lives on the `/data` volume as rebuildable
derived data. This separation is the core design rule: **derived knowledge is disposable,
contributed knowledge is durable.**

## Minimal vs full deployment

- **Agents only:** postgres + worker + mcp. (No view.)
- **Agents + humans:** add view.
- The worker and mcp **must share the `/data` volume**; that's the one hard coupling.
