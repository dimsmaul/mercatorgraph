# Acceptance / E2E Suite — Design Spec

**Project:** Mercatorgraph
**Date:** 2026-07-29
**Status:** Approved for planning
**Depends on:** Fase 1 + Fase 2 (implemented).

---

## 1. Goal

Prove the platform delivers **every feature from the PRD** — a PRD-traceable acceptance
suite that boots the real stack, runs the real pipeline (git → `graphify update` → promote →
MCP → docs), and asserts each feature. The suite plus a **coverage matrix** answers one
question: "does the app provide everything that was asked?"

Implemented features get a passing test. Not-yet / partial features are listed explicitly
(skipped/xfail) so the matrix is a complete, honest picture — not a subset that hides gaps.

## 2. Scope

- **In:** system-level acceptance tests (Python), opt-in, against the docker-compose stack;
  a coverage matrix mapping PRD → test → status.
- **Out:** browser UI interaction tests (Cypress/Playwright) — the platform's core path is
  agent→MCP, not a browser flow. Docs assertions are HTTP-level. (Playwright is the future
  choice if UI-interaction tests are added.)
- **Out:** load testing. Latency is a sample-scale sanity check, not a benchmark.

## 3. Tooling

pytest + docker compose CLI + httpx + FastMCP client. No new frontend test stack. The suite
is marked `@pytest.mark.e2e`, excluded from the default unit run, and skips if docker is
unavailable.

## 4. Components

1. **Stack fixture** (session-scoped): `docker compose up -d --build` → wait until postgres,
   worker, mcp, docs are healthy (poll `/health`, `pg_isready`, docs `/docs`) → yield →
   `docker compose down -v` in teardown (always).
2. **Sample repo** (`tests/fixtures/sample-repo/`): a small committed multi-file codebase the
   worker builds for real (exercises graphify extraction).
3. **Worker local-path repo support** (small addition): allow a filesystem `repo_url`
   (copy-tree instead of git clone) so the e2e builds the offline sample without a git host.
   ~10 lines in the clone step; also useful for local projects generally.
4. **Seed helpers**: insert a scoped token + register the project in Postgres; a FastMCP
   bearer client helper.
5. **E2E projects config** (`tests/fixtures/projects.e2e.yaml`): points `demo` at the mounted
   sample repo.

## 5. Test groups (each test = one PRD-traceable feature)

- **Build pipeline (G1, §5, §7):** rebuild → `/status` succeeded → `current` promoted;
  second build promotes new version; **validation abort keeps current** (atomic, no
  half-built graph).
- **MCP contract (§6, G2):** all 6 tools return **bounded** results; edges carry
  `EXTRACTED|INFERRED|AMBIGUOUS`; `query_graph` = scoped subgraph + summary; `get_node` = node
  + direct edges; `trace_path` = path with per-edge explanation; `blast_radius` = impacted set.
- **Auth / multi-tenancy (G4, §8):** token scoped to `demo` denied on another project;
  cross-project `search` intersected to scope; invalid token rejected; **audit_log written**.
- **Latency (G2):** `query_graph` p95 < 300 ms over N calls on the sample graph.
- **Human path (G5, Fase 2):** docs serves `/docs` + a project node page; cross-project
  `/api/search` returns hits; `/api/config` reflects runtime `WORKER_URL`; worker
  `/projects/{slug}/graph.html` returns 200 (live human artifact).

## 6. PRD Coverage Matrix

The suite ships with `tests/acceptance/PRD_COVERAGE.md`: one row per PRD feature →
`test id` → `pass | not-yet | partial`. Not-yet / partial rows are real tests marked
`skip`/`xfail` with a reason, so the file is a complete checklist.

| PRD ref | Feature | Planned status |
|---------|---------|----------------|
| §6 | `list_projects` / `query_graph` / `get_node` / `trace_path` / `blast_radius` / `search` | ✅ pass |
| §6 | size-bounded results; confidence tags on edges | ✅ pass |
| §6 | `add_annotation`, `CONTRIBUTED` overlay | ✅ pass (SP1) |
| §5/§7 | clone/pull → graphify → staging → validate → atomic promote | ✅ pass |
| §5 | trigger: webhook | ✅ pass |
| §5 | trigger: manual rebuild | ✅ pass |
| §5 | trigger: cron | ✅ pass (interval-based) |
| §7 | one-writer lock; in-mem read; incremental `--update` | ✅ pass |
| §7 | webhook debounce (open-Q1) | ✅ pass |
| §8 | token per user/agent; project scoping; audit log | ✅ pass |
| §8 | repo credentials encrypted at rest / private-repo clone | ⏳ not-yet |
| G1 | one centralized graph per project | ✅ pass |
| G2 | agent query p95 < 300 ms | ✅ pass (sample-scale) |
| G3 | knowledge persists across rebuild (annotations) | ✅ pass (SP1) |
| G4 | multi-project + multi-user auth/scope | ✅ pass |
| G5 | human-readable docs | ✅ pass |
| Fase 2 | MD→Fumadocs, per-project grouping, cross-project search, permalinks, staleness, embed | ✅ pass |
| Fase 2 | Leiden cluster **filter** (UI control) | ⚠️ partial (per-community pages only) |
| — | docs auto-regen on promote | ⏳ not-yet (deferred) |
| Fase 3 | inline comments + thread status | ✅ pass (SP2 backend) |
| Fase 3 | comment→agent→PR, diff/approval | ⏳ not-yet (SP3, needs GitHub App + LLM) |
| Fase 4 | graph diff between versions | ✅ pass (SP5) |
| Fase 4 | staleness notifications | ✅ pass (SP6) |
| Fase 4 | build & usage dashboard | ⏳ not-yet |
| Publishing | image tags, deploy compose, runtime config, CORS | ✅ pass |

## 7. Error handling

- Stack fixture: bounded health-wait with timeout; on failure, dump `docker compose logs`
  and fail fast. Teardown (`down -v`) runs in a `finally`.
- Build poll: timeout with the last `/status` payload in the failure message.
- Suite skipped entirely if `docker`/`docker compose` is absent.

## 8. Layout

```
tests/acceptance/
  conftest.py            # stack fixture, seed helpers, mcp client helper
  test_build_pipeline.py
  test_mcp_contract.py
  test_auth_scoping.py
  test_latency.py
  test_human_path.py
  PRD_COVERAGE.md        # the traceability matrix
tests/fixtures/sample-repo/            # committed sample codebase
tests/fixtures/projects.e2e.yaml
docker-compose.e2e.yml                 # overlay: mounts sample repo + e2e projects.yaml
```

## 9. Decisions

- Real build via committed sample repo + worker local-path repo support (not seeded graph).
- Opt-in `@pytest.mark.e2e`; lives in `tests/acceptance/`.
- Docs assertion = served content + `graph.html` + `/api/config`; a brand-new project does
  not auto-appear in docs (pipeline A) — documented, not asserted live.
- Coverage matrix includes **all** PRD features; not-yet/partial are skip/xfail with reasons.

## 10. Out of scope / deferred

Browser-interaction UI tests (Playwright) and load/latency benchmarking. Implementing the
not-yet features themselves (cron, debounce, cred encryption, cluster filter, auto-regen,
Fase 3/4) — the suite documents them as gaps; building them is separate work.
