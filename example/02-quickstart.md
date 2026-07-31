# 02 — Quickstart

Run the full stack from published images, index a project, and query it from an AI agent.

## 1. Get the files

Copy this `example/` folder somewhere, or just grab the three files you need:
`docker-compose.yml`, `.env.example`, `projects.example.yaml`.

```bash
cp .env.example .env
cp projects.example.yaml projects.yaml
```

Edit `.env` — at minimum set a real `POSTGRES_PASSWORD`. Then pick the image tag to run
(a published release, e.g. `0.1.1`, or `latest`):

```bash
# .env
TAG=0.1.1
```

## 2. Start the stack

```bash
docker compose up -d
```

This starts **postgres + worker + mcp + docs**. Check health:

```bash
curl -s localhost:8000/health     # worker  -> {"status":"ok"}
open http://localhost:3000/docs    # docs app (humans)
# mcp listens on :8080/mcp (bearer-token required)
```

The worker applies the database schema (migrations) automatically on startup.

## 3. Register a project + build its graph

Point `projects.yaml` at a repo the worker can reach (public HTTPS, or a private repo — see
[05-production.md](05-production.md)). Register it in Postgres and trigger the first build:

```bash
# register the project row (slug must match projects.yaml)
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "INSERT INTO projects (slug, repo_url) VALUES ('demo','https://github.com/octocat/Hello-World.git') ON CONFLICT DO NOTHING;"

# build it
curl -X POST localhost:8000/projects/demo/rebuild
curl localhost:8000/projects/demo/status     # wait until "status":"succeeded"
```

## 4. Mint a scoped agent token

Tokens are stored **hashed**. Choose a secret, hash it, insert it with the project scopes:

```bash
TOKEN="my-agent-token"
HASH=$(python3 -c "import hashlib,sys;print(hashlib.sha256('$TOKEN'.encode()).hexdigest())")

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "INSERT INTO tokens (token_hash, principal, scopes) VALUES ('$HASH','my-agent', ARRAY['demo']);"
```

Use `ARRAY['*']` instead of `ARRAY['demo']` to scope the token to every project.

## 5. Connect an AI agent (MCP)

Claude Code:

```bash
claude mcp add mercatorgraph --transport http http://localhost:8080/mcp \
  --header "Authorization: Bearer my-agent-token"
```

Or any MCP client via project `.mcp.json`:

```json
{
  "mcpServers": {
    "mercatorgraph": {
      "type": "http",
      "url": "http://localhost:8080/mcp",
      "headers": { "Authorization": "Bearer my-agent-token" }
    }
  }
}
```

Tools available: `list_projects`, `query_graph`, `get_node`, `trace_path`, `blast_radius`,
`search`, `add_annotation`, `graph_diff`.

## 6. Stop / tear down

```bash
docker compose down            # stop, keep data volumes
docker compose down -v         # stop and DELETE all data (graphs + postgres)
```

Next: [03-configuration.md](03-configuration.md) for env vars, volumes, and ports.
