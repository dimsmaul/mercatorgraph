"""Contributed-knowledge store (Postgres).

Annotations persist independently of the graph: a rebuild replaces graph.json on the
volume but never touches this table, so contributed knowledge survives (PRD G3). Read
functions tag each annotation CONTRIBUTED for overlay into query results.
"""

from __future__ import annotations

from psycopg_pool import ConnectionPool

from ckcommon.schema import Confidence

ANNOTATION_LIMIT = 50


def add_annotation(
    pool: ConnectionPool, project: str, node_id: str, content: str, principal: str
) -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO annotations (project_slug, node_id, content, principal) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (project, node_id, content, principal),
        ).fetchone()
        conn.commit()
    return row[0]


def annotations_for_nodes(
    pool: ConnectionPool, project: str, node_ids: list[str]
) -> dict[str, list[dict]]:
    if not node_ids:
        return {}
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, node_id, content, principal, status, created_at "
            "FROM annotations WHERE project_slug = %s AND node_id = ANY(%s) "
            "ORDER BY created_at",
            (project, list(node_ids)),
        ).fetchall()
    out: dict[str, list[dict]] = {}
    for id_, node_id, content, principal, status, created in rows:
        bucket = out.setdefault(node_id, [])
        if len(bucket) >= ANNOTATION_LIMIT:
            continue
        bucket.append(
            {
                "id": id_,
                "content": content,
                "principal": principal,
                "status": status,
                "created_at": created.isoformat() if created else None,
                "tag": Confidence.CONTRIBUTED.value,
            }
        )
    return out


def annotation_counts(
    pool: ConnectionPool, project: str, node_ids: list[str]
) -> dict[str, int]:
    if not node_ids:
        return {}
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT node_id, count(*) FROM annotations "
            "WHERE project_slug = %s AND node_id = ANY(%s) GROUP BY node_id",
            (project, list(node_ids)),
        ).fetchall()
    return {node_id: count for node_id, count in rows}
