"""Generate a Fumadocs MDX content tree from graphify output.

Reshapes existing artifacts only (fabricates nothing): ``graph.json`` (node-link) for
per-community and per-node pages, ``GRAPH_REPORT.md`` embedded verbatim into the project
index. Output is consumed at ``next build`` by fumadocs-mdx (pipeline A).
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

from ckcommon.schema import GRAPH_JSON, REPORT_MD, GraphEdge, GraphNode, parse_graph


def _mdx_safe(text: str) -> str:
    """Escape characters that MDX would parse as JSX/expressions.

    graphify's GRAPH_REPORT.md is plain markdown that can contain sequences like
    ``(<3 nodes)`` — a bare ``<`` starts JSX in MDX. Escaping ``<`` ``{`` ``}`` keeps the
    report rendering as text.
    """
    return text.replace("<", "&lt;").replace("{", "&#123;").replace("}", "&#125;")


def _frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            lines.append(f"{key}:")
        elif isinstance(value, list):
            inner = ", ".join(json.dumps(v) for v in value)
            lines.append(f"{key}: [{inner}]")
        else:
            lines.append(f"{key}: {json.dumps(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _dominant_confidence(edges: list[GraphEdge]) -> str | None:
    if not edges:
        return None
    counts: dict[str, int] = defaultdict(int)
    for e in edges:
        counts[e.confidence.value] += 1
    return max(counts, key=counts.get)


def _node_page(
    slug: str,
    version: str,
    node: GraphNode,
    out_edges: list[GraphEdge],
    in_edges: list[GraphEdge],
    by_id: dict[str, GraphNode],
) -> str:
    relations = sorted({e.relation for e in out_edges + in_edges})
    text = _frontmatter(
        {
            "title": node.label,
            "project": slug,
            "cluster": node.community_name,
            "tags": [node.file_type or "code", *relations],
            "confidence": _dominant_confidence(out_edges + in_edges),
            "graph_version": version,
        }
    )
    text += f"# {node.label}\n\n"
    text += f"- **File:** `{node.source_file}` {node.source_location or ''}\n"
    text += f"- **Community:** {node.community_name or '—'}\n\n"

    text += "## Outgoing\n\n"
    if out_edges:
        for e in out_edges:
            tgt = by_id.get(e.target)
            label = tgt.label if tgt else e.target
            text += (
                f"- --{e.relation}--> [{label}](/docs/{slug}/node/{e.target}) "
                f"`[{e.confidence.value}]`\n"
            )
    else:
        text += "_none_\n"

    text += "\n## Incoming\n\n"
    if in_edges:
        for e in in_edges:
            src = by_id.get(e.source)
            label = src.label if src else e.source
            text += (
                f"- [{label}](/docs/{slug}/node/{e.source}) --{e.relation}--> "
                f"`[{e.confidence.value}]`\n"
            )
    else:
        text += "_none_\n"
    return text


def generate_project(
    graphify_out_dir: str | Path,
    slug: str,
    version: str,
    out_root: str | Path,
) -> list[Path]:
    """Generate the MDX subtree for one project under ``out_root`` (content/docs).

    Rewrites only this project's ``<slug>/`` subtree and merges ``versions.json``.
    Returns the list of written files.
    """
    gdir = Path(graphify_out_dir)
    out_root = Path(out_root)
    data = json.loads((gdir / GRAPH_JSON).read_text())
    nodes, edges = parse_graph(data)

    report_path = gdir / REPORT_MD
    report_text = report_path.read_text() if report_path.exists() else ""

    proj_dir = out_root / slug
    if proj_dir.exists():
        shutil.rmtree(proj_dir)
    (proj_dir / "node").mkdir(parents=True)

    by_id = {n.id: n for n in nodes}
    out_edges: dict[str, list[GraphEdge]] = defaultdict(list)
    in_edges: dict[str, list[GraphEdge]] = defaultdict(list)
    for e in edges:
        out_edges[e.source].append(e)
        in_edges[e.target].append(e)

    communities: dict[tuple, list[GraphNode]] = defaultdict(list)
    for n in nodes:
        communities[(n.community, n.community_name)].append(n)

    written: list[Path] = []

    # per-node pages
    for n in nodes:
        page = _node_page(
            slug, version, n, out_edges.get(n.id, []), in_edges.get(n.id, []), by_id
        )
        path = proj_dir / "node" / f"{n.id}.mdx"
        path.write_text(page)
        written.append(path)

    # per-community pages
    community_files: list[str] = []
    for (cid, cname), cnodes in sorted(communities.items(), key=lambda kv: kv[0][0] or 0):
        title = cname or f"Community {cid}"
        body = _frontmatter(
            {
                "title": title,
                "project": slug,
                "cluster": cname,
                "tags": ["community"],
                "confidence": None,
                "graph_version": version,
            }
        )
        body += f"# {title}\n\n"
        for n in cnodes:
            body += f"- [{n.label}](/docs/{slug}/node/{n.id})\n"
        fname = f"community-{cid}.mdx"
        (proj_dir / fname).write_text(body)
        community_files.append(fname.removesuffix(".mdx"))
        written.append(proj_dir / fname)

    # project index
    index = _frontmatter(
        {
            "title": slug,
            "project": slug,
            "cluster": None,
            "tags": ["overview"],
            "confidence": None,
            "graph_version": version,
        }
    )
    index += f"# {slug}\n\n"
    index += f'<GraphEmbed slug="{slug}" />\n\n'
    index += "## Communities\n\n"
    for (cid, cname), _ in sorted(communities.items(), key=lambda kv: kv[0][0] or 0):
        title = cname or f"Community {cid}"
        index += f"- [{title}](/docs/{slug}/community-{cid})\n"
    index += "\n## Report\n\n"
    index += _mdx_safe(report_text)
    (proj_dir / "index.mdx").write_text(index)
    written.append(proj_dir / "index.mdx")

    # sidebar meta
    meta = {"title": slug, "pages": ["index", *community_files, "node"]}
    (proj_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    written.append(proj_dir / "meta.json")

    # staleness source
    versions_path = out_root / "versions.json"
    versions = (
        json.loads(versions_path.read_text()) if versions_path.exists() else {}
    )
    versions[slug] = version
    versions_path.write_text(json.dumps(versions, indent=2))

    return written
