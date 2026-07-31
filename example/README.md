# Mercatorgraph — Usage Guide

Turn any codebase into **one centralized, queryable knowledge graph**, served to AI agents
via a single MCP server and to developers via a docs app. Mercatorgraph wraps
[Graphify](https://github.com/Graphify-Labs/graphify) as the extraction engine — it consumes
Graphify's output, never forks it.

This folder is a self-contained guide to running Mercatorgraph from the published images.

| Guide | What it covers |
|-------|----------------|
| [01-install.md](01-install.md) | Install Docker + Compose |
| [02-quickstart.md](02-quickstart.md) | Pull images, run the stack, first build, connect an agent |
| [03-configuration.md](03-configuration.md) | Env vars, `projects.yaml`, volumes, ports, tokens |
| [04-services.md](04-services.md) | What worker / mcp / docs each do and **why they're separate** |
| [05-production.md](05-production.md) | Persistence, backups, private repos, registries |
| [docker-compose.yml](docker-compose.yml) | Ready-to-run stack using published images |
| [.env.example](.env.example) · [projects.example.yaml](projects.example.yaml) | Config templates |

---

## The big picture

```
Agent (Claude, Cursor, CI…) ──► MCP server ──► in-memory graph      (hot path, read-only)
Developer (browser)         ──► Docs app    ──► generated pages       (optional, humans only)
Git push / cron / manual    ──► Worker      ──► volume + Postgres      (build, validate, promote)
```

- **Agents only ever talk to the MCP server** — bearer token, scoped per project. They never
  touch the docs app and never get the whole graph (every result is size-capped).
- **The worker is the only writer.** It builds the graph to a staging dir, validates it, then
  flips a symlink atomically — agents never see a half-built graph.
- **Contributed knowledge** (annotations, comments) lives in Postgres and survives every
  rebuild. It is never written into the graph file.

## Why three separate services?

Short answer: they have **different jobs, different consumers, and different lifecycles**, so
they scale and deploy independently. Details in [04-services.md](04-services.md).

| Service | Language | Job | Who talks to it |
|---------|----------|-----|-----------------|
| **worker** | Python (FastAPI) | Clone/pull a repo, run Graphify, validate, promote the new graph | Git webhooks, cron, you (manual rebuild) |
| **mcp** | Python (FastMCP) | Serve the graph as fast, scoped, token-authed tools | AI agents |
| **docs** | Next.js (Fumadocs) | Human-browsable pages of the graph | Developers (browser) |
| **postgres** | — | Durable metadata: projects, builds, tokens, audit log, annotations/comments | worker + mcp (internal) |

You do **not** have to run all of them. Minimum useful setup = **postgres + worker + mcp**
(agents). Add **docs** only if you want the human browse UI.
