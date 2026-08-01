# 03 — Configuration

## Ports

| Service | Container port | Default host port | Notes |
|---------|----------------|-------------------|-------|
| worker  | 8000 | 19883 | webhook / rebuild / status / stats / graph.html |
| mcp     | 8080 | 19884 | agent MCP endpoint (`/mcp`, bearer token) |
| view    | 3000 | 19885 | human browse UI |
| postgres| 5432 | — (internal) | not exposed by default |

If a host port is taken (e.g. `8080`), remap the left side in `docker-compose.yml`
(`"8081:8080"`).

## Volumes (data that must persist)

| Volume | Mounted at | Holds | Who writes |
|--------|-----------|-------|-----------|
| `pgdata` | postgres `/var/lib/postgresql/data` | projects, builds, tokens, audit log, annotations/comments | postgres |
| `graphdata` | worker + mcp `/data` | versioned graph output (`graph.json`, report) + the `current` symlink | worker writes, mcp reads |

**`graphdata` must be shared between worker and mcp** — the worker writes new graph versions,
the mcp server reads the one the `current` symlink points at. In `docker-compose.yml` both
services mount the same named volume at `/data`.

Layout inside `graphdata`:

```
/data/projects/<slug>/versions/<timestamp>/graphify-out/graph.json
/data/projects/<slug>/current -> versions/<timestamp>     (atomic symlink)
```

Old versions are pruned (default: keep 5).

`docker compose down` keeps volumes; `down -v` deletes them.

## Environment variables (`.env`)

### Postgres

| Var | Default | Purpose |
|-----|---------|---------|
| `POSTGRES_USER` | `knowledge` | DB user |
| `POSTGRES_PASSWORD` | `change-me` | **set this** |
| `POSTGRES_DB` | `knowledge` | DB name |

`DATABASE_URL` is assembled from these in the compose file for worker + mcp.

### Images

| Var | Example | Purpose |
|-----|---------|---------|
| `IMAGE_PREFIX` | `ghcr.io/dimsmaul/mercatorgraph` | registry/namespace to pull from |
| `TAG` | `0.1.1` or `latest` | image version |

### Worker

| Var | Default | Purpose |
|-----|---------|---------|
| `DATA_DIR` | `/data` | graph volume mount |
| `PROJECTS_CONFIG` | `/app/projects.yaml` | project registry file |
| `WORKER_CORS_ORIGINS` | `*` | allowed origins for browser calls from the view app |
| `DEBOUNCE_SECONDS` | `0` | coalesce bursts of webhook pushes per project into one build (0 = off) |
| `NOTIFY_URL` | — | POST a `build.succeeded` event here on promote (Slack-compatible). Empty = off |
| `VIEW_CONTENT_DIR` | — | regenerate docs MDX into this dir after each promote. Empty = off |
| `ENCRYPTION_KEY` | — | Fernet key to decrypt repo deploy keys at rest (see 05-production) |

### MCP

| Var | Default | Purpose |
|-----|---------|---------|
| `MCP_HOST` | `0.0.0.0` | bind host |
| `MCP_PORT` | `8080` | bind port |

### View (graph viewer)

| Var | Default | Purpose |
|-----|---------|---------|
| `WORKER_URL` / `PUBLIC_WORKER_URL` | `http://localhost:19883` | browser-reachable worker URL (staleness badge + graph embed fetch it at runtime via `/api/config`) |

## `projects.yaml`

The registry of repos the worker knows how to build. Secrets are referenced by env-var name,
never inlined.

```yaml
projects:
  - slug: demo
    repo_url: https://github.com/octocat/Hello-World.git
    branch: master
    build_flags: []              # extra flags passed to `graphify update`
    webhook_secret_ref: WEBHOOK_SECRET_DEMO   # env var holding the HMAC secret
    # rebuild_interval: 3600     # optional: seconds between automatic (cron) rebuilds
    # deploy_key_ref: /run/secrets/demo_deploy.enc   # encrypted SSH key for a private repo
```

A project must also have a row in the `projects` table (see quickstart step 3) — the file
tells the worker *how* to build; the DB row is what the MCP/stats endpoints list.

## Build triggers

- **Webhook** (primary): `POST /webhook/{slug}` with a GitHub-style
  `X-Hub-Signature-256` HMAC header, verified against the project's `webhook_secret`.
- **Manual**: `POST /projects/{slug}/rebuild` (optional `?force=true`).
- **Cron**: set `rebuild_interval` (seconds) on the project.

## Tokens & scopes

- Stored as SHA-256 hashes in the `tokens` table.
- `scopes` is an array of project slugs, or `['*']` for all.
- Optional `expires_at` (timestamp) and `revoked` (bool) — the MCP verifier rejects expired or
  revoked tokens.
- Every tool call is recorded in `audit_log`.
