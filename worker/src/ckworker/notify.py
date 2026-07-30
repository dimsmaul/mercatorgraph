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
