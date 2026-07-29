# MCP server: read-only, in-memory graph. No graphify, no git.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY common ./common
COPY worker ./worker
COPY mcp ./mcp
RUN uv sync --frozen --no-dev --all-packages

ENV DATA_DIR=/data MCP_HOST=0.0.0.0 MCP_PORT=8080
EXPOSE 8080
CMD ["uv", "run", "--no-dev", "python", "-m", "ckmcp.server"]
