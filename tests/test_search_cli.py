"""Offline tests for the search CLI wrapper.

These tests use the injectable FakeOpenVikingClient so no live OpenViking
service is required.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE
from scripts.retrieval.search import cmd_search, cmd_source, cmd_trace, cmd_health


class FakeSearchClient:
    """Fake client matching the OpenVikingClient protocol with search/read/health."""

    def __init__(self):
        self.search_calls = []
        self.read_calls = []
        self._health = True

    def add_resource(self, **kwargs):
        return {"status": "completed"}

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {
            "resources": [
                {
                    "uri": f"{CORNELL_NAMESPACE}/transcript/lecture-01-abc",
                    "score": 0.92,
                    "level": 2,
                    "abstract": "This covers closed-loop transfer functions and stability criteria.",
                },
                {
                    "uri": f"{CORNELL_NAMESPACE}/notes/lecture-02-def",
                    "score": 0.85,
                    "level": 1,
                    "abstract": "Frequency response and Bode plots.",
                },
            ],
            "total": 2,
        }

    def read(self, uri, **kwargs):
        self.read_calls.append((uri, kwargs))
        return "Full source content for " + uri

    def health(self):
        return self._health


def test_cmd_search_returns_ranked_results_with_truncated_abstracts():
    client = FakeSearchClient()
    backend = CornellOpenVikingBackend(client)

    result = cmd_search(backend, "feedback stability", limit=5)

    assert result["query"] == "feedback stability"
    assert result["namespace"] == CORNELL_NAMESPACE
    assert result["total"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["uri"].startswith(CORNELL_NAMESPACE)
    assert result["results"][0]["score"] == 0.92
    assert "closed-loop" in result["results"][0]["abstract"]
    # Verify search was called with the Cornell namespace
    assert client.search_calls[0]["target_uri"] == CORNELL_NAMESPACE
    assert client.search_calls[0]["limit"] == 5


def test_cmd_source_reads_full_content_at_uri():
    client = FakeSearchClient()
    backend = CornellOpenVikingBackend(client)

    uri = f"{CORNELL_NAMESPACE}/transcript/lecture-01-abc"
    result = cmd_source(backend, uri, read_limit=10000)

    assert result["uri"] == uri
    assert "Full source content" in result["content"]
    assert client.read_calls[0][0] == uri


def test_cmd_trace_combines_search_and_top_source_read():
    client = FakeSearchClient()
    backend = CornellOpenVikingBackend(client)

    result = cmd_trace(backend, "transfer function", limit=3)

    assert result["total"] == 2
    assert "top_source" in result
    assert result["top_source"]["uri"] == result["results"][0]["uri"]
    assert "Full source content" in result["top_source"]["content"]
    # Only the top result should be read
    assert len(client.read_calls) == 1


def test_cmd_trace_with_no_results_has_no_top_source():
    empty_client = FakeSearchClient()
    empty_client.search = lambda **kw: {"resources": [], "total": 0}
    backend = CornellOpenVikingBackend(empty_client)

    result = cmd_trace(backend, "nonexistent topic", limit=5)

    assert result["total"] == 0
    assert "top_source" not in result


def test_cmd_health_reports_healthy_status():
    backend = CornellOpenVikingBackend(FakeSearchClient())
    result = cmd_health(backend)

    assert result["status"] == "healthy"
    assert result["namespace"] == CORNELL_NAMESPACE


class _BrokenHealthClient:
    """Simulates a client whose health check raises (server unreachable)."""

    def health(self):
        raise RuntimeError("server unreachable")


def test_cmd_health_reports_error_on_failure():
    """When the health check raises, cmd_health catches the error."""
    backend = CornellOpenVikingBackend(_BrokenHealthClient(), base_url="http://127.0.0.1:9999")
    result = cmd_health(backend)

    assert result["status"] == "error"
    assert "error" in result


def test_direct_search_script_help_entrypoint_runs():
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "retrieval" / "search.py"), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Cornell KB source-grounded retrieval" in completed.stdout
