# Worker: FastAPI + graphify (pinned). Needs git for clone/pull.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# graphify pinned as an isolated tool (extraction engine)
ENV UV_LINK_MODE=copy
RUN uv tool install graphifyy==0.9.28
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY common ./common
COPY worker ./worker
COPY mcp ./mcp
COPY docs-gen ./docs-gen
RUN uv sync --frozen --no-dev --all-packages

COPY db ./db
COPY projects.yaml ./

ENV DATA_DIR=/data MIGRATIONS_DIR=/app/db/migrations WORKER_HOST=0.0.0.0 WORKER_PORT=8000
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "python", "-m", "ckworker.webhook"]
