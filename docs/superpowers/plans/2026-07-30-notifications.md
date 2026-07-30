# Staleness Notifications Implementation Plan

> Use superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** When a project's graph is rebuilt+promoted, POST a notification to a configured
channel (Slack-compatible / generic webhook) so the team knows the graph changed and docs may
be stale (PRD Fase 4).

**Architecture:** A best-effort `Notifier` posts a JSON event to `NOTIFY_URL`. It is invoked
from `run_build_and_record` on success. Delivery is fire-and-forget: failures are swallowed so
a bad webhook never breaks a build. HTTP via stdlib `urllib` (no new runtime dependency).

**Tech Stack:** Python 3.12, urllib, pytest.

## Global Constraints

- Python `>=3.12`; `uv run --python 3.12 pytest`. Microcommits, no `Co-Authored-By`.
- No new runtime dependency — use stdlib `urllib.request`.
- Notifications are best-effort: never raise into the build path. No `NOTIFY_URL` = no-op.
- Reuse `run_build_and_record`; thread a `Notifier` through, don't fork build logic.

## File Structure

- `worker/src/ckworker/notify.py` — `Notifier` + default urllib poster (new).
- `worker/src/ckworker/webhook.py` — build notifier from `notify_url`, pass to all
  `run_build_and_record` call sites (modify).
- `worker/tests/test_notify.py` — notifier unit tests (new).
- `worker/tests/test_webhook.py` — notify-on-build integration (modify).
- `.env.example` — document `NOTIFY_URL` (modify).

---

## Task 1: `Notifier`

**Files:** Create `worker/src/ckworker/notify.py`; Test `worker/tests/test_notify.py`.

**Interfaces:**
- `Notifier(url: str | None, poster: Callable[[str, dict], None] | None = None)`
- `.notify(event: dict) -> None` — posts `event` to `url`; no-op if `url` falsy; swallows
  poster exceptions.
- Module `post_json(url: str, payload: dict) -> None` — default urllib poster.

- [ ] **Step 1: Failing tests** — `worker/tests/test_notify.py`:

```python
from ckworker.notify import Notifier


class FakePoster:
    def __init__(self):
        self.calls = []

    def __call__(self, url, payload):
        self.calls.append((url, payload))


def test_notify_posts_event():
    p = FakePoster()
    Notifier("http://hook", poster=p).notify({"event": "build.succeeded"})
    assert p.calls == [("http://hook", {"event": "build.succeeded"})]


def test_no_url_is_noop():
    p = FakePoster()
    Notifier(None, poster=p).notify({"x": 1})
    assert p.calls == []


def test_poster_error_is_swallowed():
    def boom(url, payload):
        raise RuntimeError("down")

    # must not raise
    Notifier("http://hook", poster=boom).notify({"x": 1})
```

- [ ] **Step 2: Run → fail** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — `worker/src/ckworker/notify.py`:

```python
"""Best-effort build/staleness notifications to a channel webhook."""

from __future__ import annotations

import json
import urllib.request
from typing import Callable

Poster = Callable[[str, dict], None]


def post_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=5).close()


class Notifier:
    def __init__(self, url: str | None, poster: Poster | None = None) -> None:
        self._url = url
        self._poster = poster or post_json

    def notify(self, event: dict) -> None:
        if not self._url:
            return
        try:
            self._poster(self._url, event)
        except Exception:  # noqa: BLE001 — notifications never break the build
            pass
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit.**

```bash
git add worker/src/ckworker/notify.py worker/tests/test_notify.py
git commit -m "feat(worker): best-effort Notifier (stdlib urllib)"
```

---

## Task 2: Notify on build success

**Files:** Modify `worker/src/ckworker/webhook.py`; Test `worker/tests/test_webhook.py`;
Modify `.env.example`.

**Interfaces:**
- `run_build_and_record(pool, slug, builder, config, force, notifier: Notifier | None = None)`
  — on success, calls `notifier.notify({...})` with `event="build.succeeded"`, `project`,
  `version_ts`, `node_count`, `edge_count`.
- `create_app(..., notify_url: str | None = None)` builds one `Notifier` and passes it to every
  `run_build_and_record` call (webhook, rebuild, debounce, cron).

- [ ] **Step 1: Failing test** — append to `worker/tests/test_webhook.py`:

```python
def test_build_sends_notification(pool, tmp_path):
    from ckworker.notify import Notifier
    from ckworker.webhook import run_build_and_record

    data_dir = str(tmp_path / "data")
    cfg = ProjectConfig(slug="demo", repo_url="https://x/demo.git", branch="main")

    def builder(slug, config, force):
        return build_project(
            slug, config, data_dir, clone_fn=noop_clone, fixture=FIXTURE, force=force
        )

    sent = []
    notifier = Notifier("http://hook", poster=lambda url, payload: sent.append(payload))
    run_build_and_record(pool, "demo", builder, cfg, False, notifier)

    assert sent, "expected a notification"
    assert sent[0]["event"] == "build.succeeded"
    assert sent[0]["project"] == "demo"
    assert sent[0]["node_count"] == 9
```

- [ ] **Step 2: Run → fail** (`run_build_and_record` takes no notifier).

- [ ] **Step 3: Implement** in `worker/src/ckworker/webhook.py`:

Add import: `from ckworker.notify import Notifier`.

Change `run_build_and_record` signature and success branch:

```python
def run_build_and_record(
    pool: ConnectionPool,
    slug: str,
    builder: Builder,
    config: ProjectConfig,
    force: bool,
    notifier: "Notifier | None" = None,
) -> None:
```

In the success `with pool.connection()` block, after the UPDATE that sets `status='succeeded'`,
add (still inside the function, after `conn.commit()`):

```python
    if notifier is not None:
        notifier.notify(
            {
                "event": "build.succeeded",
                "project": slug,
                "version_ts": outcome.version_ts,
                "node_count": outcome.node_count,
                "edge_count": outcome.edge_count,
            }
        )
```

In `create_app`, add param `notify_url: str | None = None` and near the top:

```python
    notifier = Notifier(notify_url)
```

Update all four `run_build_and_record(...)` call sites to pass `notifier`:
- webhook route: `background.add_task(run_build_and_record, pool, slug, builder, cfg, False, notifier)`
- rebuild route: `background.add_task(run_build_and_record, pool, slug, builder, cfg, force, notifier)`
- debouncer lambda: `run_build_and_record(pool, slug, builder, projects[slug], False, notifier)`
- cron lambda: `run_build_and_record(pool, slug, builder, projects[slug], False, notifier)`

In `main()`, pass `notify_url=os.environ.get("NOTIFY_URL")` to `create_app(...)`.

- [ ] **Step 4: Run → pass**, then full suite:
  `DATABASE_URL=$DB uv run --python 3.12 pytest -q` → all pass.

- [ ] **Step 5: Document + commit.** Add to `.env.example`:

```
# Notify this webhook URL on successful build/promote (Slack-compatible). Empty = off.
NOTIFY_URL=
```

```bash
git add worker/src/ckworker/webhook.py worker/tests/test_webhook.py .env.example
git commit -m "feat(worker): notify channel on successful build/promote"
```

---

## Self-Review

**Spec coverage:** Fase 4 staleness notifications → Tasks 1–2. **Placeholders:** none.
**Type consistency:** `Notifier(url, poster)` / `.notify(event)` identical between Task 1 def
and Task 2 use; `run_build_and_record(..., notifier)` signature matches all four call sites.

## Deferred
- Notify on failure / staleness thresholds; Slack block formatting; per-project channels.
