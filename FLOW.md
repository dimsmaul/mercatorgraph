# flow.md — Architecture & Data Flow

Companion to `PRD.md` and `docs/superpowers/specs/2026-07-28-fase1-mvp-design.md`.
Scope: Fase 1 (worker + MCP + Postgres, read-only).

## Component map

```mermaid
flowchart TB
  subgraph compose["docker-compose"]
    worker["worker (Python)\nregistry · clone/pull · graphify build\nstaging → validate → promote"]
    mcp["mcp (FastMCP) — HOT PATH &lt;300ms p95\ngraphstore: NetworkX + SQLite FTS\n6 tools · bearer token · scope · audit"]
    pg[("postgres\nprojects · builds · tokens · audit_log")]
    vol[("volume /data\nprojects/&lt;slug&gt;/versions/&lt;ts&gt;/ + current")]
  end

  agent(["AI Agent"]) -->|MCP tool + token| mcp
  push(["Git push webhook"]) -->|primary trigger| worker
  manual(["Manual endpoint"]) -.->|fallback trigger| worker

  worker -->|write versioned output| vol
  worker -->|build rows| pg
  mcp -->|read active graph| vol
  mcp -->|tokens · audit| pg

  classDef hot stroke:#c39;
  class mcp hot;
```

**Rule:** agents reach only the MCP server. No tool returns the whole graph.

## Build path (heavy, rare — one writer per project)

```mermaid
flowchart TB
  a["push webhook"] --> b{"verify HMAC sig\nvs webhook_secret"}
  b -->|bad| bx["reject"]
  b -->|ok| c["enqueue · acquire per-project lock\n(2nd build queues or rejects)"]
  c --> d["clone (first) / pull (subsequent)\nread-only deploy key"]
  d --> e["graphify build → STAGING\ndata/projects/&lt;slug&gt;/versions/&lt;ts&gt;/\nflags: --code-only --update"]
  e --> f{"validate staging\njson parses? node_count&gt;0?\nno big unexplained drop?"}
  f -->|no| fx["abort promote\nbuilds.status=failed\ncurrent untouched"]
  f -->|yes| g["atomic promote:\nflip 'current' symlink (single rename)"]
  g --> h["notify mcp reload + builds row (succeeded)"]
  h --> i["prune versions beyond retention (N=5)"]
```

Graphify lives behind `worker/graphify_adapter.py` only. Version pinned in Dockerfile.
⚠️ Headless build command (`--code-only` graph.json in CI) must be confirmed against the
pinned Graphify version — see spec §2.1.

## Query path (light, concurrent, read-only)

```mermaid
flowchart TB
  a["agent: MCP tool call + bearer token"] --> b{"auth: hash-lookup token\n→ principal + scopes"}
  b -->|invalid| bx["reject + audit attempt"]
  b -->|valid| c{"scope check:\nproject ∈ scopes (or '*')"}
  c -->|no| cx["deny"]
  c -->|yes| d["run tool against in-memory graphstore\n→ result size-capped"]
  d --> e["append audit_log\n(principal, tool, project, args, ts)"]
  e --> f["return bounded result"]
```

## Graph hot-reload

```mermaid
flowchart LR
  p["promote event"] --> b["build NEW graphstore\nfrom 'current' version"]
  b --> s["atomically swap active reference"]
  s --> o["in-flight reads finish on OLD store\n(never see half-built graph)"]
```

## Tools (Fase 1, deterministic — no LLM in MCP)

| Tool | What it does |
|------|--------------|
| `list_projects` | projects + last_build + node/edge counts |
| `query_graph` | FTS seed → depth-limited BFS neighborhood, capped `max_nodes` → subgraph + deterministic summary |
| `get_node` | node detail + direct edges |
| `trace_path` | shortest path(s), per-edge relation + confidence + explanation |
| `blast_radius` | reverse-reachability within depth, ranked by cached betweenness centrality |
| `search` | SQLite FTS; no `project` = cross-project, intersected with token scopes |

`add_annotation` = Fase 3, not in Fase 1.

## Storage split

| Kind | Source | Where | Lifecycle |
|------|--------|-------|-----------|
| Derived | Graphify | volume `data/projects/<slug>/versions/<ts>/` + `current` symlink | rebuildable, overwritten, retained N=5 |
| Metadata | platform | Postgres (projects, builds, tokens, audit_log) | durable |
| FTS index | derived from graph | SQLite, in mcp | ephemeral, rebuilt per graph load |
| Contributed | humans/agents | Postgres `annotations` (Fase 3, table stubbed now) | durable, overlaid at query time |

Edge confidence tags `EXTRACTED | INFERRED | AMBIGUOUS` are preserved through every layer.
