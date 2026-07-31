"""Docs-side inline comments — persisted in the shared `annotations` table.

Human comments and agent annotations share one store; a comment is an annotation with a
thread status. Status transitions: open -> addressed-by-agent -> resolved.
"""

from __future__ import annotations

from psycopg_pool import ConnectionPool

VALID_STATUS = {"open", "addressed-by-agent", "resolved"}


def add_comment(
    pool: ConnectionPool, project: str, node_id: str, content: str, author: str
) -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO annotations (project_slug, node_id, content, principal, status) "
            "VALUES (%s, %s, %s, %s, 'open') RETURNING id",
            (project, node_id, content, author),
        ).fetchone()
        conn.commit()
    return row[0]


def list_comments(
    pool: ConnectionPool, project: str, node_id: str | None = None
) -> list[dict]:
    query = (
        "SELECT id, node_id, content, principal, status, created_at "
        "FROM annotations WHERE project_slug = %s"
    )
    params: list = [project]
    if node_id:
        query += " AND node_id = %s"
        params.append(node_id)
    query += " ORDER BY created_at"
    with pool.connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "id": i,
            "node_id": n,
            "content": c,
            "author": p,
            "status": s,
            "created_at": cr.isoformat() if cr else None,
        }
        for i, n, c, p, s, cr in rows
    ]


def set_status(
    pool: ConnectionPool, project: str, comment_id: int, status: str
) -> bool:
    """Update a comment's status, scoped to its project (prevents cross-tenant writes)."""
    if status not in VALID_STATUS:
        raise ValueError(f"invalid status {status!r}")
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE annotations SET status = %s WHERE id = %s AND project_slug = %s "
            "RETURNING id",
            (status, comment_id, project),
        ).fetchone()
        conn.commit()
    return row is not None
