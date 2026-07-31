# 05 — Production notes

## Persistence & backups

Two things hold real state:

- **`pgdata`** (Postgres) — projects, tokens, audit log, and **contributed knowledge**
  (annotations/comments). This is the irreplaceable data. Back it up:
  ```bash
  docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
  ```
- **`graphdata`** (`/data`) — the built graphs. Rebuildable from source, so a backup is
  optional; losing it just means re-running the builds.

Use named volumes (as in the example compose) or bind-mount to host paths you back up. Never
run `docker compose down -v` in production unless you intend to wipe everything.

## Private repositories (encrypted deploy keys)

The worker can clone private repos over SSH using a deploy key that is **encrypted at rest**.

1. Generate an encryption key once and put it in the worker env as `ENCRYPTION_KEY`:
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Encrypt your SSH private key with it and store the ciphertext on the worker (a mounted
   file or a Docker secret), e.g. `/run/secrets/demo_deploy.enc`.
3. Reference it in `projects.yaml`:
   ```yaml
   - slug: demo
     repo_url: git@github.com:acme/private-repo.git
     deploy_key_ref: /run/secrets/demo_deploy.enc
   ```

At build time the worker decrypts the key to a temporary `0600` file and uses it only for that
clone. Plaintext keys are never persisted.

## Webhook security

Set a per-project HMAC secret (env var named by `webhook_secret_ref`). The worker verifies the
GitHub-style `X-Hub-Signature-256` header and rejects unsigned/mismatched pushes.

## Exposure & auth boundary

- The **MCP server** is the authenticated surface for agents (bearer token + per-project
  scope + audit).
- The **worker HTTP endpoints** (`/status`, `/rebuild`, `/stats/*`, `/graph.html`) are
  currently **unauthenticated** — they are meant to sit on an internal network, not the public
  internet. Put them behind a reverse proxy / network policy if exposed.

## Registries

Images are published to two registries by CI:

- **GHCR** (always): `ghcr.io/dimsmaul/mercatorgraph/{worker,mcp,docs}:<version>`
- **Docker Hub** (if configured): `dimsmaul/mercatorgraph:{worker,mcp,docs}-<version>`
  — one repo, service encoded in the tag (Docker Hub has no sub-paths).

Set `IMAGE_PREFIX` + `TAG` in `.env` to choose what the stack pulls. For Docker Hub's
service-in-tag scheme, reference images explicitly (see the commented block in
[docker-compose.yml](docker-compose.yml)).

## Notifications

Set `NOTIFY_URL` to receive a JSON `build.succeeded` event on every promote — useful to alert
a channel that a project's graph (and therefore its docs) changed.

## Docs freshness (pipeline A)

The view app compiles content at **image build time**. A newly built project does not appear
in a running view container until the view image is rebuilt with regenerated content. Set
`VIEW_CONTENT_DIR` so the worker regenerates the MDX on promote, then rebuild/redeploy the view image on your schedule. The staleness badge surfaces the lag in the meantime.
