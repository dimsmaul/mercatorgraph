"""Per-project build debounce.

For repos with high push frequency, coalesce a burst of pushes into a single build.
Trailing debounce: each trigger (re)starts a per-project timer; the build runs once the
project has been quiet for ``delay`` seconds. The per-project build lock still serializes
any builds that do fire.

Only used when ``delay > 0``. At ``delay <= 0`` the webhook path keeps its immediate
(non-debounced) behavior and does not construct this.
"""

from __future__ import annotations

import threading
from typing import Callable

Runner = Callable[[str], None]


class BuildDebouncer:
    def __init__(self, delay: float, runner: Runner) -> None:
        if delay <= 0:
            raise ValueError("BuildDebouncer requires delay > 0")
        self._delay = delay
        self._runner = runner
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def trigger(self, slug: str) -> None:
        """Schedule (or reschedule) a build for ``slug`` after the quiet window."""
        with self._lock:
            existing = self._timers.get(slug)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(self._delay, self._fire, args=(slug,))
            timer.daemon = True
            self._timers[slug] = timer
            timer.start()

    def _fire(self, slug: str) -> None:
        with self._lock:
            self._timers.pop(slug, None)
        self._runner(slug)

    def pending(self, slug: str) -> bool:
        with self._lock:
            return slug in self._timers

    def flush(self) -> None:
        """Cancel all pending timers (shutdown / tests)."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
