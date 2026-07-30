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
