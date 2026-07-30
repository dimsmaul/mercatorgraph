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

    Notifier("http://hook", poster=boom).notify({"x": 1})
