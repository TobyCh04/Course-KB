"""Execute validated Cornell query plans without trusting planner output."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

try:
    from .openviking_backend import CORNELL_NAMESPACE, CornellOpenVikingBackend
    from .hybrid_retrieval import (
        DEFAULT_EXPERIMENTAL_RERANK_TOP,
        select_final_sources,
    )
    from .query_models import PlanningResult, QueryPlan, QueryTrace
except ImportError:  # pragma: no cover - exercised by direct CLI use
    from openviking_backend import CORNELL_NAMESPACE, CornellOpenVikingBackend
    from hybrid_retrieval import DEFAULT_EXPERIMENTAL_RERANK_TOP, select_final_sources
    from query_models import PlanningResult, QueryPlan, QueryTrace

HindsightRecall = Callable[[str, int], Any]


def execute_planned_query(
    planning: PlanningResult,
    backend: CornellOpenVikingBackend,
    *,
    index_path: str | Path = "data/lexical_index.json",
    hindsight_recall: HindsightRecall | None = None,
    max_sources: int = 8,
    blend_rrf_weight: float | None = None,
    blend_reranker_weight: float = 0.30,
    enable_reranker: bool = False,
) -> dict[str, Any]:
    """Execute validated plan with one role-aware hybrid call per OpenViking plan."""
    plan, trace = planning.plan, planning.trace
    if max_sources < 1:
        raise ValueError("max_sources must be positive")
    merged: dict[str, dict[str, Any]] = {}

    def merge_result(result: dict[str, Any], provenance: list[str]) -> None:
        for candidate in result.get("results", []):
            uri = candidate.get("canonical_uri") or candidate.get("uri", "")
            if not uri or not uri.startswith(CORNELL_NAMESPACE):
                continue
            candidate = dict(candidate)
            candidate.setdefault("query_provenance", []).extend(provenance)
            existing = merged.get(uri)
            if existing is None or _candidate_score(candidate) > _candidate_score(existing):
                merged[uri] = candidate

    openviking_queries = [
        query for query in plan.queries
        if "openviking" in ((query.backend,) if query.backend else plan.backends)
    ]
    if openviking_queries:
        started = time.monotonic()
        record: dict[str, Any] = {
            "query": plan.original_query,
            "query_role": "hybrid" if len(openviking_queries) > 1 else openviking_queries[0].role,
            "queries": [
                {"text": query.text, "role": query.role}
                for query in openviking_queries
            ],
            "original_query": plan.original_query,
            "trace_id": plan.trace_id,
            "backend": "openviking",
            "status": "started",
        }
        try:
            lexical = next((q for q in openviking_queries if q.role == "lexical"), None)
            semantic = next((q for q in openviking_queries if q.role == "semantic"), None)
            result = _execute_openviking(
                backend,
                plan.original_query,
                plan,
                index_path=index_path,
                dense_query=semantic.text if semantic else None,
                lexical_query=lexical.text if lexical else None,
                blend_rrf_weight=blend_rrf_weight,
                blend_reranker_weight=blend_reranker_weight,
                enable_reranker=enable_reranker,
            )
            provenance = [query.text for query in openviking_queries]
            merge_result(result, provenance)
            record["result_count"] = len(result.get("results", []))
            record["mode"] = result.get("mode")
            record["source_read_failures"] = result.get("source_read_failures", [])
            record["status"] = "completed"
        except Exception as error:
            record["status"] = "failed"
            trace.add_error(f"openviking query failed: {error}")
        record["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
        trace.execution.append(record)

    for planned_query in plan.queries:
        selected_backends = (planned_query.backend,) if planned_query.backend else plan.backends
        for backend_name in selected_backends:
            if backend_name == "openviking":
                continue
            started = time.monotonic()
            record = {
                "query": planned_query.text,
                "query_role": planned_query.role,
                "original_query": plan.original_query,
                "trace_id": plan.trace_id,
                "backend": backend_name,
                "status": "started",
            }
            try:
                if backend_name == "hindsight":
                    if hindsight_recall is None:
                        raise RuntimeError("Hindsight backend requested but no recall callable configured")
                    memories = hindsight_recall(planned_query.text, plan.limit)
                    record["result_count"] = len(memories) if isinstance(memories, list) else 0
                    record["memories"] = memories
                else:
                    raise RuntimeError(f"unsupported execution backend: {backend_name}")
                record["status"] = "completed"
            except Exception as error:
                record["status"] = "failed"
                trace.add_error(f"{backend_name} query failed: {error}")
            record["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
            trace.execution.append(record)

    candidates = sorted(merged.values(), key=_candidate_score, reverse=True)
    if candidates:
        final_sources, source_cutoff = select_final_sources(
            candidates,
            default_limit=plan.limit,
            max_sources=max_sources,
            reranked=any("rerank_score" in item for item in candidates),
        )
    else:
        final_sources, source_cutoff = [], {}
    trace.source_uris = [item.get("uri", "") for item in final_sources if item.get("uri")]
    if trace.status == "planned" and any(item.get("status") == "failed" for item in trace.execution):
        trace.status = "partial_failure"
    return {
        "query": plan.original_query,
        "namespace": CORNELL_NAMESPACE,
        "plan": plan.to_dict(),
        "trace": trace.to_dict(),
        "source_cutoff": source_cutoff,
        "results": final_sources,
    }


def _execute_openviking(
    backend: CornellOpenVikingBackend,
    query: str,
    plan: QueryPlan,
    *,
    index_path: str | Path,
    dense_query: str | None = None,
    lexical_query: str | None = None,
    blend_rrf_weight: float | None = None,
    blend_reranker_weight: float = 0.30,
    enable_reranker: bool = False,
) -> dict[str, Any]:
    if plan.retrieval_mode == "dense":
        raw = backend.search(dense_query or query, limit=plan.limit)
        return {"mode": "dense", "results": raw.get("resources", [])}
    return backend.hybrid_search(
        query,
        index_path=index_path,
        top_k=plan.limit,
        max_sources=8,
        dense_query=dense_query,
        lexical_query=lexical_query,
        blend_rrf_weight=blend_rrf_weight,
        blend_reranker_weight=blend_reranker_weight,
        rerank_top=DEFAULT_EXPERIMENTAL_RERANK_TOP
        if enable_reranker and plan.retrieval_mode == "hybrid_rerank"
        else 0,
    )


def _candidate_score(candidate: dict[str, Any]) -> float:
    return float(candidate.get("rerank_score", candidate.get("fused_score", candidate.get("score", 0.0))))


__all__ = ["execute_planned_query"]
