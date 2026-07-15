import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_json_http_client_retries_transient_failure_with_exponential_backoff():
    from scripts.common_client import JsonHttpClient, TransientHttpError

    attempts = []
    delays = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def opener(request, timeout):
        attempts.append((request.full_url, timeout))
        if len(attempts) < 3:
            raise TransientHttpError("temporarily unavailable")
        return Response({"ok": True})

    client = JsonHttpClient(opener=opener, timeout=11, retries=2, backoff_seconds=0.25, sleep=delays.append)

    assert client.post_json("https://example.test/endpoint", {"value": 1}) == {"ok": True}
    assert attempts == [
        ("https://example.test/endpoint", 11),
        ("https://example.test/endpoint", 11),
        ("https://example.test/endpoint", 11),
    ]
    assert delays == [0.25, 0.5]
