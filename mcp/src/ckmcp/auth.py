"""Token auth + project scoping + audit for the MCP server.

Tokens are stored as sha256 hashes. Every tool call resolves a bearer token to a principal
and its scopes, checks project scope, and writes an audit row.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from psycopg_pool import ConnectionPool

WILDCARD = "*"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class TokenInfo:
    principal: str
    scopes: list[str]


def lookup_token(pool: ConnectionPool, raw_token: str) -> TokenInfo | None:
    """Resolve a bearer token to principal + scopes, updating last_used_at.
    Returns None if the token is unknown."""
    token_hash = hash_token(raw_token)
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE tokens SET last_used_at = now() WHERE token_hash = %s "
            "AND revoked = false AND (expires_at IS NULL OR expires_at > now()) "
            "RETURNING principal, scopes",
            (token_hash,),
        ).fetchone()
    if row is None:
        return None
    return TokenInfo(principal=row[0], scopes=list(row[1]))


def check_scope(project: str, scopes: list[str]) -> bool:
    return WILDCARD in scopes or project in scopes


def allowed_projects(scopes: list[str], all_projects: list[str]) -> list[str]:
    """Intersect a caller's scopes with the set of known projects.
    Used for cross-project search."""
    if WILDCARD in scopes:
        return list(all_projects)
    return [p for p in all_projects if p in scopes]


def audit(
    pool: ConnectionPool,
    principal: str | None,
    tool: str,
    project: str | None,
    args_summary: str | None = None,
) -> None:
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO audit_log (principal, tool, project_slug, args_summary) "
            "VALUES (%s, %s, %s, %s)",
            (principal, tool, project, args_summary),
        )
        conn.commit()
