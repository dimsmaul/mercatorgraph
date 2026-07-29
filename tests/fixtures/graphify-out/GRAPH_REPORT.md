# Graph Report - gbig  (2026-07-28)

## Corpus Check
- 4 files · ~46 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 9 nodes · 18 edges · 2 communities (1 shown, 1 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- api.py
- auth.py

## God Nodes (most connected - your core abstractions)
1. `handle()` - 5 edges
2. `verify()` - 4 edges
3. `save()` - 4 edges
4. `conn()` - 4 edges
5. `main()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `handle()`  [EXTRACTED]
  main.py → svc/api.py
- `handle()` --calls--> `save()`  [EXTRACTED]
  svc/api.py → svc/db.py
- `verify()` --calls--> `conn()`  [EXTRACTED]
  svc/auth.py → svc/db.py
- `handle()` --calls--> `verify()`  [EXTRACTED]
  svc/api.py → svc/auth.py

## Import Cycles
- None detected.

## Communities (2 total, 1 thin omitted)

### Community 0 - "api.py"
Cohesion: 0.70
Nodes (3): main(), handle(), verify()

## Knowledge Gaps
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `handle()` connect `api.py` to `auth.py`?**
  _High betweenness centrality (0.232) - this node is a cross-community bridge._
- **Why does `verify()` connect `api.py` to `auth.py`?**
  _High betweenness centrality (0.086) - this node is a cross-community bridge._
- **Why does `save()` connect `auth.py` to `api.py`?**
  _High betweenness centrality (0.086) - this node is a cross-community bridge._