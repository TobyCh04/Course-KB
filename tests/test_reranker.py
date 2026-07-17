"""Offline tests for the reranking layer.

Uses a fake cross-encoder and fake OpenViking client. No model downloads
or live OpenViking service required.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE
from scripts import reranker as reranker_mod


class FakeSearchClient:
    """Fake OpenViking client returning a fixed set of candidates."""

    def __init__(self, candidates=None):
        self._candidates = candidates if candidates is not None else [
            {"uri": f"{CORNELL_NAMESPACE}/doc/alpha", "score": 0.80, "level": 1,
             "abstract": "Alpha: lean manufacturing overview."},
            {"uri": f"{CORNELL_NAMESPACE}/doc/beta", "score": 0.85, "level": 1,
             "abstract": "Beta: kanban calculation formula and examples."},
            {"uri": f"{CORNELL_NAMESPACE}/doc/gamma", "score": 0.75, "level": 2,
             "abstract": "Gamma: constraint management theory."},
            {"uri": f"{CORNELL_NAMESPACE}/doc/delta", "score": 0.90, "level": 1,
             "abstract": "Delta: frequency response and Bode plots."},
            {"uri": f"{CORNELL_NAMESPACE}/doc/epsilon", "score": 0.70, "level": 2,
             "abstract": "Epsilon: house of lean framework."},
        ]

    def add_resource(self, **kwargs):
        return {"status": "completed"}

    def search(self, **kwargs):
        return {"resources": list(self._candidates), "total": len(self._candidates)}

    def read(self, uri, **kwargs):
        return f"Content of {uri}"

    def health(self):
        return True


class FakeCrossEncoder:
    """Fake cross-encoder that scores pairs by keyword overlap."""

    def __init__(self, model_name):
        self.model_name = model_name

    def predict(self, pairs):
        scores = []
        for query, doc in pairs:
            query_words = set(query.lower().split())
            doc_words = set(doc.lower().split())
            overlap = len(query_words & doc_words)
            scores.append(float(overlap * 0.1))
        return scores


@pytest.fixture(autouse=True)
def _patch_reranker(monkeypatch):
    """Patch the reranker loader so tests never download a model."""
    monkeypatch.setattr(reranker_mod, "_get_reranker", lambda name: FakeCrossEncoder(name))
    # Reset module-level cache
    monkeypatch.setattr(reranker_mod, "_reranker_model", None)
    monkeypatch.setattr(reranker_mod, "_reranker_model_name", None)


def test_rerank_candidates_reorders_by_cross_encoder_score():
    candidates = [
        {"uri": f"{CORNELL_NAMESPACE}/doc/a", "score": 0.9, "abstract": "frequency response"},
        {"uri": f"{CORNELL_NAMESPACE}/doc/b", "score": 0.7, "abstract": "kanban pull system"},
        {"uri": f"{CORNELL_NAMESPACE}/doc/c", "score": 0.8, "abstract": "lean manufacturing kanban"},
    ]
    result = reranker_mod.rerank_candidates("kanban pull", candidates, top_k=2)

    # FakeCrossEncoder scores by word overlap: "kanban" appears in b and c.
    # b: 1 overlap (kanban), c: 2 overlaps (kanban + lean? no, query is "kanban pull")
    # query words: {kanban, pull} — b has {kanban, pull, system}, overlap=2
    # c has {lean, manufacturing, kanban}, overlap=1
    assert len(result) == 2
    assert "rerank_score" in result[0]
    # b should rank first (2 overlaps) over c (1 overlap)
    assert result[0]["uri"].endswith("/doc/b")
    assert result[1]["uri"].endswith("/doc/c")


def test_rerank_candidates_returns_all_when_fewer_than_top_k():
    candidates = [
        {"uri": f"{CORNELL_NAMESPACE}/doc/a", "score": 0.9, "abstract": "alpha"},
        {"uri": f"{CORNELL_NAMESPACE}/doc/b", "score": 0.7, "abstract": "beta"},
    ]
    result = reranker_mod.rerank_candidates("query", candidates, top_k=5)
    # Should return both without calling the cross-encoder.
    assert len(result) == 2
    assert "rerank_score" not in result[0]  # no reranking happened


def test_rerank_candidates_falls_back_on_exception(monkeypatch):
    candidates = [
        {"uri": f"{CORNELL_NAMESPACE}/doc/a", "score": 0.9, "abstract": "alpha"},
        {"uri": f"{CORNELL_NAMESPACE}/doc/b", "score": 0.7, "abstract": "beta"},
        {"uri": f"{CORNELL_NAMESPACE}/doc/c", "score": 0.8, "abstract": "gamma"},
    ]

    def _raising_get_reranker(name):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(reranker_mod, "_get_reranker", _raising_get_reranker)

    result = reranker_mod.rerank_candidates("query", candidates, top_k=2)
    # Fallback: sorted by dense score, no rerank_score field.
    assert len(result) == 2
    assert result[0]["score"] == 0.9  # highest dense score first
    assert "rerank_score" not in result[0]


def test_search_with_rerank_returns_reranked_results():
    backend = CornellOpenVikingBackend(FakeSearchClient())
    result = reranker_mod.search_with_rerank(
        backend, "kanban", search_limit=5, rerank_top=3,
    )
    assert result["total_candidates"] == 5
    assert result["mode"] == "dense_plus_reranker"
    assert len(result["results"]) == 3
    assert "rerank_score" in result["results"][0]
    assert "rerank_latency_ms" in result


def test_search_with_rerank_dense_only_mode():
    backend = CornellOpenVikingBackend(FakeSearchClient())
    result = reranker_mod.search_with_rerank(
        backend, "kanban", search_limit=5, rerank_top=3,
        use_reranker=False,
    )
    assert result["mode"] == "dense_only"
    assert len(result["results"]) == 3
    assert "rerank_score" not in result["results"][0]


def test_search_with_rerank_empty_results():
    empty_client = FakeSearchClient(candidates=[])
    backend = CornellOpenVikingBackend(empty_client)
    result = reranker_mod.search_with_rerank(
        backend, "nonexistent", search_limit=5, rerank_top=3,
    )
    assert result["total_candidates"] == 0
    assert result["results"] == []


def test_ab_comparison_shows_order_difference():
    backend = CornellOpenVikingBackend(FakeSearchClient())
    result = reranker_mod.cmd_ab_comparison(
        backend, "kanban", search_limit=5, rerank_top=3,
    )
    assert "dense_only" in result
    assert "dense_plus_reranker" in result
    assert "order_changed" in result
    assert len(result["dense_only"]["top_uris"]) == 3
    assert len(result["dense_plus_reranker"]["top_uris"]) == 3


def test_reranker_cannot_escape_namespace():
    """Reranker only reorders candidates from OpenViking; it cannot introduce
    new URIs. All URIs must come from the Cornell namespace search."""
    backend = CornellOpenVikingBackend(FakeSearchClient())
    result = reranker_mod.search_with_rerank(
        backend, "kanban", search_limit=5, rerank_top=3,
    )
    for r in result["results"]:
        assert r["uri"].startswith(CORNELL_NAMESPACE)

def test_server_mode_falls_back_when_server_unreachable(monkeypatch):
    """When --server is set but the server is unreachable, fall back to dense ranking."""
    def _raising_urlopen(req, timeout=None):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(reranker_mod.urllib.request, "urlopen", _raising_urlopen)

    candidates = [
        {"uri": f"{CORNELL_NAMESPACE}/doc/a", "score": 0.9, "abstract": "alpha"},
        {"uri": f"{CORNELL_NAMESPACE}/doc/b", "score": 0.7, "abstract": "beta"},
        {"uri": f"{CORNELL_NAMESPACE}/doc/c", "score": 0.8, "abstract": "gamma"},
    ]
    result = reranker_mod.rerank_candidates(
        "query", candidates, top_k=2, server_url="localhost:9999",
    )
    assert len(result) == 2
    assert result[0]["score"] == 0.9
    assert "rerank_score" not in result[0]
