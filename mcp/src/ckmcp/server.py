"""FastMCP server: DB-backed bearer auth + the 6 scoped graph tools.

Tools are declared async so the authenticated identity (a contextvar) is read in the async
context, then the sync Tools logic (Postgres + networkx) runs in a threadpool.
"""

from __future__ import annotations

import os

import anyio
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from psycopg_pool import ConnectionPool

from ckcommon.db import get_pool
from ckmcp import auth
from ckmcp.registry import FsGraphRegistry
from ckmcp.tools import Tools


class DbTokenVerifier(TokenVerifier):
    """Verify a bearer token against the tokens table. Project scopes ride in `scopes`."""

    def __init__(self, pool: ConnectionPool) -> None:
        super().__init__()
        self._pool = pool

    async def verify_token(self, token: str) -> AccessToken | None:
        info = await anyio.to_thread.run_sync(auth.lookup_token, self._pool, token)
        if info is None:
            return None
        return AccessToken(
            token=token,
            client_id=info.principal,
            scopes=list(info.scopes),
            subject=info.principal,
            claims={"principal": info.principal},
        )


def current_token() -> auth.TokenInfo:
    at = get_access_token()
    if at is None:
        raise PermissionError("missing or invalid bearer token")
    return auth.TokenInfo(principal=at.client_id, scopes=list(at.scopes))


def build_server(pool: ConnectionPool, data_dir: str) -> FastMCP:
    registry = FsGraphRegistry(data_dir)
    tools = Tools(registry, pool)
    mcp: FastMCP = FastMCP(name="mercatorgraph", auth=DbTokenVerifier(pool))

    @mcp.tool
    async def list_projects() -> list[dict]:
        """List indexed projects visible to the caller with last-build stats."""
        tok = current_token()
        return await anyio.to_thread.run_sync(tools.list_projects, tok)

    @mcp.tool
    async def query_graph(project: str, question: str, max_nodes: int | None = None) -> dict:
        """Scoped subgraph + summary for a question about a project."""
        tok = current_token()
        return await anyio.to_thread.run_sync(
            tools.query_graph, tok, project, question, max_nodes
        )

    @mcp.tool
    async def get_node(project: str, node_id: str) -> dict:
        """Node detail plus its direct edges and any contributed annotations."""
        tok = current_token()
        return await anyio.to_thread.run_sync(tools.get_node, tok, project, node_id)

    @mcp.tool
    async def add_annotation(project: str, node_id: str, content: str) -> dict:
        """Attach a persistent note to a node (contributed knowledge)."""
        tok = current_token()
        return await anyio.to_thread.run_sync(
            tools.add_annotation, tok, project, node_id, content
        )

    @mcp.tool
    async def trace_path(
        project: str, from_node: str, to_node: str, max_paths: int | None = None
    ) -> dict:
        """Explained path(s) between two nodes."""
        tok = current_token()
        return await anyio.to_thread.run_sync(
            tools.trace_path, tok, project, from_node, to_node, max_paths
        )

    @mcp.tool
    async def blast_radius(project: str, node_id: str, depth: int | None = None) -> dict:
        """Nodes impacted if this node changes, ranked by centrality."""
        tok = current_token()
        return await anyio.to_thread.run_sync(
            tools.blast_radius, tok, project, node_id, depth
        )

    @mcp.tool
    async def search(query: str, project: str | None = None, limit: int | None = None) -> dict:
        """Full-text search over nodes + report. Omit project for cross-project (scoped)."""
        tok = current_token()
        return await anyio.to_thread.run_sync(tools.search, tok, query, project, limit)

    @mcp.tool
    async def graph_diff(
        project: str, from_version: str | None = None, to_version: str | None = None
    ) -> dict:
        """What changed between two graph versions (defaults to the last two)."""
        tok = current_token()
        return await anyio.to_thread.run_sync(
            tools.graph_diff, tok, project, from_version, to_version
        )

    return mcp


def main() -> None:
    pool = get_pool()
    data_dir = os.environ.get("DATA_DIR", "/data")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    server = build_server(pool, data_dir)
    server.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
