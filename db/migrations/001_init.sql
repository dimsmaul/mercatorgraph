-- Fase 1 metadata schema.
-- Derived knowledge (graph.json + MD) lives on the volume, NOT here.
-- This DB holds durable metadata only.

CREATE TABLE IF NOT EXISTS projects (
    slug                TEXT PRIMARY KEY,
    repo_url            TEXT NOT NULL,
    branch              TEXT NOT NULL DEFAULT 'main',
    build_flags         JSONB NOT NULL DEFAULT '[]',
    webhook_secret_ref  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS builds (
    id            BIGSERIAL PRIMARY KEY,
    project_slug  TEXT NOT NULL REFERENCES projects(slug) ON DELETE CASCADE,
    version_ts    TEXT NOT NULL,
    status        TEXT NOT NULL,              -- running | succeeded | failed
    node_count    INTEGER,
    edge_count    INTEGER,
    error         TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS builds_project_started_idx
    ON builds (project_slug, started_at DESC);

CREATE TABLE IF NOT EXISTS tokens (
    id            BIGSERIAL PRIMARY KEY,
    token_hash    TEXT UNIQUE NOT NULL,       -- sha256 hex of the bearer token
    principal     TEXT NOT NULL,              -- user or agent name
    scopes        TEXT[] NOT NULL DEFAULT '{}', -- project slugs, or {'*'}
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            BIGSERIAL PRIMARY KEY,
    principal     TEXT,
    tool          TEXT NOT NULL,
    project_slug  TEXT,
    args_summary  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_created_idx ON audit_log (created_at DESC);

-- Fase 3 stub: contributed knowledge. Created now to keep the
-- derived-vs-contributed split visible from day one. Unused in Fase 1.
CREATE TABLE IF NOT EXISTS annotations (
    id            BIGSERIAL PRIMARY KEY,
    project_slug  TEXT REFERENCES projects(slug) ON DELETE CASCADE,
    node_id       TEXT,
    content       TEXT NOT NULL,
    principal     TEXT,
    status        TEXT NOT NULL DEFAULT 'open',  -- open | addressed-by-agent | resolved
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
