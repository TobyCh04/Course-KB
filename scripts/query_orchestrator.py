"""Execute validated Cornell query plans without trusting planner output."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .openviking_backend import CORNELL_NAMESPACE, CornellOpenVikingBackend
from .hybrid_retrieval import select_final_sources
from .query_models import PlanningResult, QueryPlan, QueryTrace

HindsightRecall = Callable[[str, int], Any]


def execute_planned_query(
    planning: PlanningResult,
    backend: CornellOpenVikingBackend,
    *,
    index_path: str | Path = "data/lexical_index.json",
    hindsight_recall: HindsightRecall | None = None,
    max_sources: int = 8,
) -> dict[str, Any]:
    """Execute plan and return results plus visible planner/execution trace.

    Backend calls are limited to validated plan backends. OpenViking remains
    namespace-locked by its adapter; Hindsight is injected for offline tests
    and deployment-specific integration.
    """
    plan, trace = planning.plan, planning.trace
    if max_sources < 1:
        raise ValueError("max_sources must be positive")
    merged: dict[str, dict[str, Any]] = {}

    for planned_query in plan.queries:
        selected_backends = (planned_query.backend,) if planned_query.backend else plan.backends
        for backend_name in selected_backends:
            started = time.monotonic()
            record: dict[str, Any] = {
                "query": planned_query.text,
                "query_role": planned_query.role,
                "original_query": plan.original_query,
                "trace_id": plan.trace_id,
                "backend": backend_name,
                "status": "started",
            }
            try:
                if backend_name == "openviking":
                    result = _execute_openviking(
                        backend,
                        planned_query.text,
                        plan,
                        index_path=index_path,
                    )
                    candidates = result.get("results", [])
                    for candidate in candidates:
                        uri = candidate.get("canonical_uri") or candidate.get("uri", "")
                        if not uri or not uri.startswith(CORNELL_NAMESPACE):
                            continue
                        candidate = dict(candidate)
                        candidate.setdefault("query_provenance", []).append(planned_query.text)
                        existing = merged.get(uri)
                        if existing is None or _candidate_score(candidate) > _candidate_score(existing):
                            merged[uri] = candidate
                    record["result_count"] = len(candidates)
                    record["mode"] = result.get("mode")
                elif backend_name == "hindsight":
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
) -> dict[str, Any]:
    if plan.retrieval_mode == "dense":
        raw = backend.search(query, limit=plan.limit)
        return {"mode": "dense", "results": raw.get("resources", [])}
    return backend.hybrid_search(
        query,
        index_path=index_path,
        top_k=plan.limit,
    )


def _candidate_score(candidate: dict[str, Any]) -> float:
    return float(candidate.get("rerank_score", candidate.get("fused_score", candidate.get("score", 0.0))))


__all__ = ["execute_planned_query"]
