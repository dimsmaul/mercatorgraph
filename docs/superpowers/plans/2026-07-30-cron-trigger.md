# Cron Trigger Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Periodic (interval-based) automatic rebuilds per project — the "cron" trigger listed in PRD §5, alongside the existing webhook + manual triggers.

**Architecture:** Each project may declare a `rebuild_interval` (seconds) in `projects.yaml`.
A worker-side `CronScheduler` fires a rebuild for each such project on its interval, reusing
the existing `run_build_and_record` path (so the build lock + validation + promote all apply).
Started on FastAPI startup, stopped on shutdown.

**Tech Stack:** Python 3.12, threading.Timer, FastAPI lifespan events, pytest.

## Global Constraints

- Python `>=3.12`; `uv run --python 3.12 pytest`. Microcommits, no `Co-Authored-By`.
- Reuse `run_build_and_record(pool, slug, builder, cfg, force)` — do not duplicate build logic.
- `rebuild_interval <= 0` or unset = no cron for that project (backward compatible).
- Timer-based tests use small intervals + polling (no fixed sleeps that race the work).

## File Structure

- `common/src/ckcommon/config.py` — add `rebuild_interval` to `ProjectConfig` (modify).
- `worker/src/ckworker/cron.py` — `CronScheduler` (new).
- `worker/src/ckworker/webhook.py` — build + start/stop scheduler in `create_app` (modify).
- `common/tests/test_config.py` — interval parsing (modify).
- `worker/tests/test_cron.py` — scheduler unit tests (new).
- `worker/tests/test_webhook.py` — wired cron integration (modify).

---

## Task 1: `rebuild_interval` config field

**Files:** Modify `common/src/ckcommon/config.py`; Test `common/tests/test_config.py`.

**Interfaces:** `ProjectConfig.rebuild_interval: int | None` (seconds; default None). Parsed
from yaml key `rebuild_interval`.

- [ ] **Step 1: Failing test** — append to `common/tests/test_config.py`:

```python
def test_rebuild_interval_parsed(tmp_path):
    import textwrap
    p = tmp_path / "projects.yaml"
    p.write_text(textwrap.dedent("""
        projects:
          - slug: demo
            repo_url: https://x/demo.git
            rebuild_interval: 3600
          - slug: other
            repo_url: https://x/other.git
    """))
    projects = load_projects(p)
    assert projects["demo"].rebuild_interval == 3600
    assert projects["other"].rebuild_interval is None
```

- [ ] **Step 2: Run → fail.** `uv run --python 3.12 pytest common/tests/test_config.py -k interval -v` → AttributeError.

- [ ] **Step 3: Implement.** In `ProjectConfig` add field after `webhook_secret_ref`:

```python
    rebuild_interval: int | None = None
```

In `_project_from_dict(...)` add:

```python
        rebuild_interval=raw.get("rebuild_interval"),
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit.**

```bash
git add common/src/ckcommon/config.py common/tests/test_config.py
git commit -m "feat(common): project rebuild_interval config"
```

---

## Task 2: `CronScheduler`

**Files:** Create `worker/src/ckworker/cron.py`; Test `worker/tests/test_cron.py`.

**Interfaces:**
- `CronScheduler(runner: Callable[[str], None])`
- `.schedule(slug: str, interval: float) -> None` (no-op if `interval <= 0`); repeats until stopped.
- `.scheduled() -> set[str]`; `.stop() -> None`.

- [ ] **Step 1: Failing test** — `worker/tests/test_cron.py`:

```python
import threading
import time

from ckworker.cron import CronScheduler


class Counter:
    def __init__(self):
        self.calls = []
        self._lock = threading.Lock()

    def __call__(self, slug):
        with self._lock:
            self.calls.append(slug)


def test_repeats_on_interval():
    c = Counter()
    s = CronScheduler(c)
    s.schedule("demo", 0.1)
    time.sleep(0.35)  # ~3 fires
    s.stop()
    assert c.calls.count("demo") >= 2


def test_zero_interval_is_noop():
    c = Counter()
    s = CronScheduler(c)
    s.schedule("demo", 0)
    assert s.scheduled() == set()
    time.sleep(0.15)
    assert c.calls == []


def test_stop_halts_further_fires():
    c = Counter()
    s = CronScheduler(c)
    s.schedule("demo", 0.1)
    time.sleep(0.15)
    s.stop()
    n = len(c.calls)
    time.sleep(0.25)
    assert len(c.calls) == n
```

- [ ] **Step 2: Run → fail** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — `worker/src/ckworker/cron.py`:

```python
"""Interval-based rebuild scheduler (the PRD 'cron' trigger).

Reschedules a per-project timer after each fire. Reuses the standard build path via the
injected runner, so the build lock + validation + promote all still apply.
"""

from __future__ import annotations

import threading
from typing import Callable

Runner = Callable[[str], None]


class CronScheduler:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner
        self._intervals: dict[str, float] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, slug: str, interval: float) -> None:
        if interval <= 0:
            return
        with self._lock:
            self._intervals[slug] = interval
        self._arm(slug)

    def _arm(self, slug: str) -> None:
        with self._lock:
            interval = self._intervals.get(slug)
            if interval is None:
                return
            timer = threading.Timer(interval, self._fire, args=(slug,))
            timer.daemon = True
            self._timers[slug] = timer
            timer.start()

    def _fire(self, slug: str) -> None:
        try:
            self._runner(slug)
        finally:
            if slug in self._intervals:
                self._arm(slug)

    def scheduled(self) -> set[str]:
        return set(self._intervals)

    def stop(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
            self._intervals.clear()
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit.**

```bash
git add worker/src/ckworker/cron.py worker/tests/test_cron.py
git commit -m "feat(worker): interval-based CronScheduler"
```

---

## Task 3: Wire cron into the worker app

**Files:** Modify `worker/src/ckworker/webhook.py`; Test `worker/tests/test_webhook.py`.

**Interfaces:** `create_app(..., start_cron: bool = False)`. When `start_cron` is true, a
`CronScheduler` is built, every project with `rebuild_interval > 0` is scheduled with runner
`run_build_and_record(pool, slug, builder, cfg, False)`, started on FastAPI startup and stopped
on shutdown. Exposed as `app.state.cron`.

- [ ] **Step 1: Failing test** — append to `worker/tests/test_webhook.py`:

```python
def test_cron_triggers_rebuild(pool, tmp_path, monkeypatch):
    data_dir = str(tmp_path / "data")
    cfg = ProjectConfig(
        slug="demo", repo_url="https://x/demo.git", branch="main", rebuild_interval=0.15
    )

    def builder(slug, config, force):
        return build_project(
            slug, config, data_dir, clone_fn=noop_clone, fixture=FIXTURE, force=force
        )

    app = create_app(pool, data_dir, {"demo": cfg}, builder=builder, start_cron=True)
    with TestClient(app):  # startup fires scheduling; shutdown stops it
        deadline = time.time() + 5
        n = 0
        while time.time() < deadline:
            with pool.connection() as conn:
                n = conn.execute(
                    "SELECT count(*) FROM builds WHERE project_slug='demo' "
                    "AND status='succeeded'"
                ).fetchone()[0]
            if n >= 1:
                break
            time.sleep(0.05)
    assert n >= 1
```

- [ ] **Step 2: Run → fail** (`create_app` has no `start_cron`).

- [ ] **Step 3: Implement** in `worker/src/ckworker/webhook.py`:

Add import: `from ckworker.cron import CronScheduler`.

Change the signature:

```python
def create_app(
    pool: ConnectionPool,
    data_dir: str,
    projects: dict[str, ProjectConfig],
    builder: Builder | None = None,
    debounce_seconds: float = 0.0,
    start_cron: bool = False,
) -> FastAPI:
```

After the debouncer block, before defining routes, add:

```python
    cron: CronScheduler | None = None
    if start_cron:
        cron = CronScheduler(
            lambda slug: run_build_and_record(pool, slug, builder, projects[slug], False)
        )
        app.state.cron = cron

        @app.on_event("startup")
        def _start_cron() -> None:
            for slug, cfg in projects.items():
                if cfg.rebuild_interval:
                    cron.schedule(slug, cfg.rebuild_interval)

        @app.on_event("shutdown")
        def _stop_cron() -> None:
            cron.stop()
```

In `main()`, pass `start_cron=True`:

```python
    app = create_app(
        pool, data_dir, all_projects(), debounce_seconds=debounce, start_cron=True
    )
```

- [ ] **Step 4: Run → pass.** Then full suite:
  `DATABASE_URL=$DB uv run --python 3.12 pytest -q` → all pass.

- [ ] **Step 5: Commit.**

```bash
git add worker/src/ckworker/webhook.py worker/tests/test_webhook.py
git commit -m "feat(worker): start cron scheduler on app startup"
```

Also document `rebuild_interval` in `.env.example`/`projects.yaml` comment (fold into this commit).

---

## Self-Review

**Spec coverage:** PRD §5 cron trigger → Tasks 1–3. **Placeholders:** none. **Type
consistency:** `rebuild_interval` (Task 1) read in Task 3; `CronScheduler(runner)` /
`.schedule` / `.stop` identical between Task 2 def and Task 3 use.

## Deferred
- Real crontab expressions (only fixed intervals here).
- Debounce interaction: cron uses the same build lock, so a cron build and a webhook build
  serialize; no coalescing between the two paths (acceptable).
