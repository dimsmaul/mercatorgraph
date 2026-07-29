# Fase 2 — Docs App Design Spec

**Project:** Centralized Codebase Knowledge Platform (Graphify-based)
**Phase:** Fase 2 — Human-readable docs app (Fumadocs)
**Date:** 2026-07-28
**Status:** Approved for implementation (pipeline **A**)
**Depends on:** Fase 1 (worker + MCP + storage) — complete.

---

## 1. Goal & Scope

Give developers a browsable, filterable, cross-project view of the knowledge graph, so they
read structure instead of raw files. Humans only — agents never touch this app (they use MCP).

**In scope:**
- Content generator: `graph.json` + `GRAPH_REPORT.md` → Fumadocs MDX tree.
- Fumadocs (Next.js) app: per-project grouping, per-community pages, per-node pages with
  stable permalinks, cross-project search, staleness badge, subgraph embed.
- Worker regenerates content after each promote; a `docs` service serves it.

**Out of scope:**
- Comments / annotations / any write path (Fase 3).
- Agent access (MCP only).
- LLM anything.

**Exit criteria:** ≥2 projects rendered; browse project → community → node; cross-project
search returns hits; stale page shows a badge; a node's subgraph embed renders.

---

## 2. Grounded content source

graphify 0.9.28 has **no `--wiki`** (the earlier idealized doc was wrong). Content comes from
two artifacts already produced every build:

- **`GRAPH_REPORT.md`** — structured markdown: `## Summary`, `## Community Hubs`,
  `## God Nodes`, `## Surprising Connections`, `## Import Cycles`, `## Communities` (per
  community: cohesion + node list). Good as-is; embedded verbatim into the project index page.
- **`graph.json`** — node-link (Fase 1 schema). Source for per-community grouping (node
  `community` / `community_name`) and per-node pages (label, source_file, edges).
- **`graph.html`** — graphify's interactive viz; reused via iframe for the subgraph embed.

The generator therefore **fabricates nothing** — it reshapes existing artifacts.

---

## 3. Pipeline decision: A (build-time MDX)

Generator writes MDX into the docs app's `content/docs/`; `next build` compiles via
`fumadocs-mdx`. On a graph promote, the worker regenerates content and the docs app is
rebuilt. The **staleness badge** models the lag between "graph last built" and "this page
last generated", which is exactly the build-time model.

---

## 4. Generator (`ckdocs`, Python)

New workspace package `docs-gen/` (`ckdocs`), depends only on `ckcommon` (reuses
`schema.parse_graph`). No dependency on `ckmcp`.

**API:** `generate_project(graphify_out_dir, slug, version, out_root) -> list[Path]`.

**Output tree** (`out_root` = docs app `content/docs`):
```
content/docs/<slug>/
  index.mdx                 # frontmatter + embedded GRAPH_REPORT.md + nav links
  meta.json                 # fumadocs sidebar order for this project
  community-<id>.mdx        # per Leiden community: name + node list (links)
  node/<node_id>.mdx        # per node: label, file:loc, in/out edges w/ relation+confidence
content/docs/versions.json  # { "<slug>": "<version_ts>" }  (staleness source)
```

**Frontmatter (every page):**
```yaml
title: <human title>
project: <slug>
cluster: <community_name | null>
tags: [<file_type>, <relations…>]
confidence: <dominant edge confidence for node pages | null>
graph_version: <version_ts>
```

**Rules:**
- Filenames use node `id` (safe slug); titles use `label`.
- Permalink is path-derived and stable: `/docs/<slug>/node/<id>`.
- Node page lists incoming + outgoing edges, each with `relation` + confidence tag.
- Community pages group by `community`; title = `community_name`.
- Index embeds `GRAPH_REPORT.md` verbatim under a heading + links to communities/top nodes.
- Idempotent: regenerating a project clears and rewrites its `<slug>/` subtree only.

---

## 5. Fumadocs app (`docs/`, bun)

Standalone Next.js app in `docs/`, **bun** for install/build/dev (scaffolded manually to
avoid the `create-fumadocs-app` bunx bug). Uses `fumadocs-ui` + `fumadocs-mdx` +
`fumadocs-core`.

- **Grouping:** each project = a folder under `content/docs/<slug>` → sidebar section;
  `meta.json` controls order.
- **Search:** Fumadocs built-in (Orama) over all generated MDX → cross-project.
- **Staleness badge:** a client component `StaleBadge` reads the page's `graph_version`
  (from frontmatter, passed as prop) and fetches the worker `GET /projects/{slug}/status`
  at runtime; if the latest succeeded build's `version_ts` > page `graph_version`, show
  "graph updated since this page was generated".
- **Subgraph embed:** MDX component `<GraphEmbed slug=… />` renders an `<iframe>` of the
  project's `graph.html` served by the worker (new static route, see §6).
- Standalone `@/components/ui/*` per project skeleton convention (not `@workspace/ui`).

---

## 6. Wiring

- **Worker static route** (small addition): `GET /projects/{slug}/graph.html` serves
  `current/graphify-out/graph.html` for the embed iframe. (Also enables the "cheap view".)
- **Regeneration:** after `promote`, worker runs `ckdocs.generate_project(...)` into a
  content volume shared with the docs build. For MVP the docs app is rebuilt on demand
  (`docker compose build docs`); automatic rebuild-on-promote is a later refinement.
- **Compose:** add `docs` service (Next standalone output) + shared `content` volume.

---

## 7. Testing

- **Generator (pytest):** fixture `graphify-out` → assert index/community/node files exist,
  frontmatter fields present, permalinks stable, `versions.json` written, edges rendered
  with confidence tags, regeneration is idempotent.
- **App:** `next build` succeeds over generated content; a smoke check that a node route and
  search index exist. (Heavier UI e2e deferred.)

---

## 8. Module / repo layout additions

```
docs-gen/                       # ckdocs generator (python, workspace member)
  pyproject.toml
  src/ckdocs/generator.py
  tests/test_generator.py
docs/                           # Fumadocs Next app (bun, isolated)
  package.json  source.config.ts  next.config.mjs
  app/…  content/docs/…  components/{StaleBadge,GraphEmbed}.tsx
  Dockerfile
```

---

## 9. Deferred

- Auto rebuild-on-promote (webhook → docs image rebuild/redeploy).
- Richer staleness (per-node changed-since-diff) — Fase 4 graph diff.
- Comments/threads — Fase 3.
- Replacing the `graph.html` iframe with a native React subgraph component.
