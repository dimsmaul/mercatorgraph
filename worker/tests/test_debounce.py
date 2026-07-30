import threading
import time

import pytest

from ckworker.debounce import BuildDebouncer


class Counter:
    def __init__(self):
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, slug: str) -> None:
        with self._lock:
            self.calls.append(slug)


def test_requires_positive_delay():
    with pytest.raises(ValueError):
        BuildDebouncer(0, lambda s: None)


def test_burst_coalesces_to_one_build():
    c = Counter()
    d = BuildDebouncer(0.15, c)
    for _ in range(5):
        d.trigger("demo")
        time.sleep(0.02)  # all within the 0.15s window
    assert d.pending("demo") is True
    time.sleep(0.3)
    assert c.calls == ["demo"]  # coalesced to a single build
    assert d.pending("demo") is False


def test_separate_projects_are_independent():
    c = Counter()
    d = BuildDebouncer(0.1, c)
    d.trigger("a")
    d.trigger("b")
    time.sleep(0.3)
    assert sorted(c.calls) == ["a", "b"]


def test_trigger_after_fire_runs_again():
    c = Counter()
    d = BuildDebouncer(0.1, c)
    d.trigger("demo")
    time.sleep(0.25)
    d.trigger("demo")
    time.sleep(0.25)
    assert c.calls == ["demo", "demo"]


def test_flush_cancels_pending():
    c = Counter()
    d = BuildDebouncer(0.2, c)
    d.trigger("demo")
    d.flush()
    time.sleep(0.3)
    assert c.calls == []
