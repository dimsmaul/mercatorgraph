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
    time.sleep(0.35)
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
