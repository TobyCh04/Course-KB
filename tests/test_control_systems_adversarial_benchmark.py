"""Contract tests for the real control-systems adversarial benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_runs.control_systems_adversarial_benchmark import (
    DEFAULT_CORPUS,
    DEFAULT_QUERIES,
    _read_source,
    _load_manifest,
    run_benchmark,
)


pytestmark = pytest.mark.skipif(
    not DEFAULT_CORPUS.is_file() or not DEFAULT_QUERIES.is_file(),
    reason="optional adversarial benchmark corpus was cleaned; regenerate it for benchmark tests",
)


def test_real_control_corpus_has_all_requested_material_types() -> None:
    sources = _load_manifest(DEFAULT_CORPUS, "sources")
    assert len(sources) == 22
    assert len({source["id"] for source in sources}) == 22
    assert {source["source_type"] for source in sources} >= {
        "note", "note_sources", "textbook", "lecture", "homework", "exam",
    }
    for source in sources:
        path = Path(source["path"])
        assert path.is_file(), source["id"]
        assert _read_source(path).strip(), source["id"]


def test_adversarial_queries_reference_existing_evidence_and_cases() -> None:
    sources = _load_manifest(DEFAULT_CORPUS, "sources")
    queries = _load_manifest(DEFAULT_QUERIES, "queries")
    source_by_id = {source["id"]: Path(source["path"]) for source in sources}

    assert len(queries) >= 12
    assert len({query["id"] for query in queries}) == len(queries)
    case_types = {query["case_type"] for query in queries}
    assert {"near_duplicate", "multi_source", "partial_evidence"} <= case_types
    assert sum(query["case_type"] == "near_duplicate" for query in queries) >= 4
    assert sum(query["case_type"] == "multi_source" for query in queries) >= 2

    for query in queries:
        expected = set(query["expected_sources"])
        assert expected
        assert expected <= set(source_by_id), query["id"]
        assert set(query.get("distractor_sources", [])) <= set(source_by_id), query["id"]
        for evidence in query["required_evidence"]:
            assert evidence["source_id"] in source_by_id, query["id"]
            text = _read_source(source_by_id[evidence["source_id"]]).casefold()
            assert evidence["terms"], query["id"]
            assert all(str(term).casefold() in text for term in evidence["terms"]), query["id"]


def test_real_material_lexical_smoke_isolated_from_production() -> None:
    result = run_benchmark(DEFAULT_CORPUS, DEFAULT_QUERIES, include_semantic=False)
    assert result["corpus"]["source_count"] == 22
    assert result["corpus"]["query_count"] >= 12
    assert result["corpus"]["production_services_accessed"] is False
    assert result["corpus"]["source_paths_verified"] is True
    assert result["strategies"]["lexical_only"]["queries"] == result["corpus"]["query_count"]
    assert "multi_source" in result["strategies"]["lexical_only"]["by_case_type"]
    assert "near_duplicate" in result["strategies"]["lexical_only"]["by_case_type"]
