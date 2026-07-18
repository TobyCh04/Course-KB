"""Offline tests for hybrid retrieval (RRF fusion and CLI wiring).

Uses fake OpenViking and fake lexical index; no model downloads or live server.
"""

import sys
from pathlib import Path

from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE
from scripts import hybrid_retrieval as hr
from scripts.lexical_index import LexicalIndex, save_index
from scripts.search import cmd_hybrid, cmd_hybrid_trace


class FakeSearchClient:
    """Fake OpenViking client returning fixed candidates."""

    def __init__(self, candidates=None):
        self._candidates = candidates if candidates is not None else [
            {"uri": f"{CORNELL_NAMESPACE}/doc/alpha/alpha.md", "score": 0.80, "level": 1,
             "abstract": "Alpha: lean manufacturing overview."},
            {"uri": f"{CORNELL_NAMESPACE}/doc/beta/beta.md", "score": 0.85, "level": 1,
             "abstract": "Beta: kanban calculation formula and examples."},
            {"uri": f"{CORNELL_NAMESPACE}/doc/gamma/gamma.md", "score": 0.75, "level": 2,
             "abstract": "Gamma: constraint management theory."},
        ]

    def add_resource(self, **kwargs):
        return {"status": "completed"}

    def search(self, **kwargs):
        return {"resources": list(self._candidates), "total": len(self._candidates)}

    def read(self, uri, **kwargs):
        return f"Content of {uri}"

    def health(self):
        return True


def _write_lexical_index(tmp_path, query_results: dict[str, list[dict[str, Any]]]) -> Path:
    """Write a fake BM25 index that ignores the query and returns the stored list."""
    index = LexicalIndex(
        corpus_tokens=[["placeholder"]],
        uris=["viking://resources/cornell-kb/placeholder"],
        abstracts=["placeholder"],
        metadata=[{}],
    )
    # Monkeypatch the search method for testing.
    def _fake_search(query, top_k=10):
        return query_results.get(query, [])
    index.search = _fake_search
    path = tmp_path / "lexical_index.json"
    save_index(index, path)
    return path


def test_reciprocal_rank_fusion_boosts_documents_in_both_lists():
    dense = [
        {"uri": "viking://resources/cornell-kb/a", "score": 0.9, "abstract": "a"},
        {"uri": "viking://resources/cornell-kb/b", "score": 0.8, "abstract": "b"},
    ]
    lexical = [
        {"uri": "viking://resources/cornell-kb/b", "score": 0.7, "abstract": "b"},
        {"uri": "viking://resources/cornell-kb/c", "score": 0.6, "abstract": "c"},
    ]
    merged = hr.reciprocal_rank_fusion(dense, lexical)

    assert len(merged) == 3
    assert merged[0]["uri"] == "viking://resources/cornell-kb/b"
    assert len(merged[0]["provenance"]) == 2  # present in both lists


def test_reciprocal_rank_fusion_respects_weights():
    dense = [
        {"uri": "viking://resources/cornell-kb/a", "score": 0.9, "abstract": "a"},
    ]
    lexical = [
        {"uri": "viking://resources/cornell-kb/b", "score": 0.9, "abstract": "b"},
    ]
    merged = hr.reciprocal_rank_fusion(dense, lexical, dense_weight=2.0, lexical_weight=1.0)
    assert merged[0]["uri"] == "viking://resources/cornell-kb/a"
    assert merged[1]["uri"] == "viking://resources/cornell-kb/b"


def test_reciprocal_rank_fusion_merges_chunk_resources_by_canonical_uri():
    """Dense URIs from OpenViking chunks and lexical URIs from the BM25 index
    share the same parent directory but differ in the trailing filename.
    RRF must merge them via canonical_uri, not treat them as separate docs."""
    dense = [
        {"uri": "viking://resources/cornell-kb/cornell-source/data-abc/freq_1.md",
         "canonical_uri": "viking://resources/cornell-kb/cornell-source/data-abc",
         "score": 0.9, "abstract": "chunk 1"},
        {"uri": "viking://resources/cornell-kb/cornell-source/data-abc/freq_2.md",
         "canonical_uri": "viking://resources/cornell-kb/cornell-source/data-abc",
         "score": 0.85, "abstract": "chunk 2"},
    ]
    lexical = [
        {"uri": "viking://resources/cornell-kb/cornell-source/data-abc/freq_response.json",
         "canonical_uri": "viking://resources/cornell-kb/cornell-source/data-abc",
         "score": 0.8, "abstract": "whole doc"},
    ]
    merged = hr.reciprocal_rank_fusion(dense, lexical)

    # All three candidates should merge into one entry.
    assert len(merged) == 1
    assert len(merged[0]["provenance"]) == 3  # 2 dense + 1 lexical
    assert merged[0]["canonical_uri"] == "viking://resources/cornell-kb/cornell-source/data-abc"


def test_dedupe_by_canonical_uri_keeps_highest_scoring_chunk():
    """Multiple chunks from the same source document should collapse to one."""
    results = [
        {"uri": "viking://resources/cornell-kb/doc/data-abc/chunk_1.md",
         "canonical_uri": "viking://resources/cornell-kb/doc/data-abc",
         "score": 0.9, "abstract": "chunk 1"},
        {"uri": "viking://resources/cornell-kb/doc/data-abc/chunk_2.md",
         "canonical_uri": "viking://resources/cornell-kb/doc/data-abc",
         "score": 0.7, "abstract": "chunk 2"},
        {"uri": "viking://resources/cornell-kb/doc/other-xyz/single.md",
         "canonical_uri": "viking://resources/cornell-kb/doc/other-xyz",
         "score": 0.8, "abstract": "other"},
    ]
    deduped = hr._dedupe_by_canonical_uri(results)
    assert len(deduped) == 2
    assert deduped[0]["uri"].endswith("chunk_1.md")  # highest score kept
    assert deduped[1]["uri"].endswith("single.md")


def test_hybrid_search_returns_fused_results(tmp_path, monkeypatch):
    backend = CornellOpenVikingBackend(FakeSearchClient())
    lexical_results = [
        {"uri": f"{CORNELL_NAMESPACE}/doc/alpha", "score": 0.9, "abstract": "alpha"},
    ]
    index_path = _write_lexical_index(tmp_path, {})

    def _fake_lexical_search(query, index_path, *, limit=10):
        return lexical_results

    monkeypatch.setattr(hr, "lexical_search", _fake_lexical_search)

    result = hr.hybrid_search(
        backend, "kanban", index_path=index_path,
        search_limit=3, lexical_limit=3, top_k=3,
    )

    assert result["query"] == "kanban"
    assert result["mode"] == "dense_plus_lexical"
    assert result["dense_candidates"] == 3
    assert result["lexical_candidates"] == 1
    assert len(result["results"]) <= 3
    # All URIs should be in the Cornell namespace.
    for r in result["results"]:
        assert r["uri"].startswith(CORNELL_NAMESPACE)


def test_hybrid_search_reranker_flag(tmp_path, monkeypatch):
    backend = CornellOpenVikingBackend(FakeSearchClient())
    lexical_results = {"kanban": []}
    index_path = _write_lexical_index(tmp_path, lexical_results)

    rerank_called = []

    def _fake_rerank(query, candidates, **kwargs):
        rerank_called.append((query, candidates, kwargs))
        for c in candidates:
            c["rerank_score"] = 1.0
        return candidates

    monkeypatch.setattr(hr.reranker_mod, "rerank_candidates", _fake_rerank)

    result = hr.hybrid_search(
        backend, "kanban", index_path=index_path,
        search_limit=3, lexical_limit=3, top_k=3, rerank_top=2,
    )

    assert result["mode"] == "dense_lexical_reranker"
    assert "rerank_latency_ms" in result
    assert rerank_called


def test_cmd_hybrid_wires_backend_and_index(tmp_path):
    backend = CornellOpenVikingBackend(FakeSearchClient())
    lexical_results = {"kanban": []}
    index_path = _write_lexical_index(tmp_path, lexical_results)

    result = cmd_hybrid(
        backend, "kanban",
        index_path=str(index_path),
        limit=3, lexical_limit=3, top_k=3, k=60,
        dense_weight=1.0, lexical_weight=1.0,
        rerank_top=0, rerank_server="",
    )
    assert result["query"] == "kanban"


def test_cmd_hybrid_trace_reads_top_fused_result(tmp_path):
    backend = CornellOpenVikingBackend(FakeSearchClient())
    lexical_results = {"kanban": []}
    index_path = _write_lexical_index(tmp_path, lexical_results)

    result = cmd_hybrid_trace(
        backend, "kanban",
        index_path=str(index_path),
        limit=3, lexical_limit=3, top_k=3, k=60,
        dense_weight=1.0, lexical_weight=1.0,
        read_limit=1000,
    )
    assert "top_source" in result
    assert result["top_source"]["uri"] == result["results"][0]["uri"]
    assert "Content of" in result["top_source"]["content"]
