"""Safe, injectable LLM query planner for Cornell KB.

The planner never executes a backend and never trusts raw model output. It
returns a validated plan, retry-visible trace, and deterministic fallback when
both planner attempts fail.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable, Mapping

from .openviking_backend import CORNELL_NAMESPACE
from .query_models import (
    FILTER_KEYS,
    PlannedQuery,
    PlanningResult,
    QueryFilters,
    QueryPlan,
    QueryTrace,
    SUPPORTED_BACKENDS,
    SUPPORTED_INTENTS,
    SUPPORTED_MODES,
)

PlannerLLM = Callable[[str], str]
_MAX_PROMPT_QUERY = 4000
_MAX_REWRITTEN_QUERY = 1000
_ALLOWED_RESPONSE_KEYS = frozenset({"intent", "backends", "queries", "filters", "retrieval_mode", "limit"})
_COURSE_RE = re.compile(r"\b[A-Z]{2,8}\s*\d{4}\b")
_LECTURE_RE = re.compile(r"\blecture\s*(?:number\s*)?(\d{1,4})\b", re.IGNORECASE)


class PlannerValidationError(ValueError):
    """Raised when model output cannot become a safe QueryPlan."""


class QueryPlanner:
    """Plan one query using current-main-model callable, with visible fallback."""

    def __init__(
        self,
        llm: PlannerLLM | None = None,
        *,
        model: str | None = None,
        provider: str | None = None,
        max_attempts: int = 2,
        default_limit: int = 5,
    ) -> None:
        if max_attempts < 1 or max_attempts > 2:
            raise ValueError("max_attempts must be 1 or 2")
        if not 1 <= default_limit <= 20:
            raise ValueError("default_limit must be between 1 and 20")
        self.llm = llm
        self.model = model
        self.provider = provider
        self.max_attempts = max_attempts
        self.default_limit = default_limit

    def plan(self, original_query: str) -> PlanningResult:
        query = original_query.strip()
        trace_id = uuid.uuid4().hex
        trace = QueryTrace(original_query=query, trace_id=trace_id)
        if not query:
            raise PlannerValidationError("original query cannot be empty")

        if self.llm is None:
            trace.status = "planner_failed"
            trace.fallback_used = True
            trace.warning = "Query planner unavailable. Used original query with deterministic retrieval."
            trace.add_error("no planner LLM callable configured")
            return PlanningResult(self._fallback(query, trace_id), trace)

        prompt = self._build_prompt(query)
        for attempt in range(1, self.max_attempts + 1):
            trace.planner_attempts = attempt
            try:
                raw = self.llm(prompt)
                plan = self._parse_and_validate(raw, query, trace_id)
                trace.status = "planned"
                return PlanningResult(plan, trace)
            except Exception as error:
                trace.add_error(f"attempt {attempt}: {error}")

        trace.status = "planner_failed"
        trace.fallback_used = True
        trace.warning = (
            f"Query planner failed after {trace.planner_attempts} attempts. "
            "Used original query with deterministic hybrid retrieval and reranking."
        )
        return PlanningResult(self._fallback(query, trace_id), trace)

    def validate_model_response(
        self,
        original_query: str,
        raw_response: str,
        *,
        trace_id: str | None = None,
    ) -> PlanningResult:
        """Validate a plan already produced by the active Hermes model.

        This path is for skill use: Hermes' current turn/model produces the
        JSON, then this module validates it without opening any model client.
        """
        query = original_query.strip()
        if not query:
            raise PlannerValidationError("original query cannot be empty")
        trace = QueryTrace(original_query=query, trace_id=trace_id or uuid.uuid4().hex)
        try:
            plan = self._parse_and_validate(raw_response, query, trace.trace_id)
        except Exception as error:
            trace.status = "planner_failed"
            trace.fallback_used = True
            trace.planner_attempts = 1
            trace.add_error(error)
            trace.warning = (
                "Active Hermes model returned an invalid query plan. "
                "Used original query with deterministic hybrid retrieval and reranking."
            )
            return PlanningResult(self._fallback(query, trace.trace_id), trace)
        trace.status = "planned"
        trace.planner_attempts = 1
        return PlanningResult(plan, trace)

    def _build_prompt(self, query: str) -> str:
        return f"""Plan Cornell KB retrieval. Return ONLY one JSON object.
Do not answer the user. Do not invent course, lecture, semester, date, source,
or namespace filters. Preserve formulas, symbols, and course codes.

Allowed intent: {sorted(SUPPORTED_INTENTS)}
Allowed backends: {sorted(SUPPORTED_BACKENDS)}
Allowed retrieval_mode: {sorted(SUPPORTED_MODES)}
Allowed filter keys: course, lecture, source_type, semester, date
JSON shape:
{{
  "intent": "document_lookup",
  "backends": ["openviking"],
  "queries": [{{"text": "...", "role": "retrieval"}}],
  "filters": {{}},
  "retrieval_mode": "hybrid_rerank",
  "limit": 5
}}

Original user query:
{query[:_MAX_PROMPT_QUERY]}"""

    def _parse_and_validate(self, raw: str, original_query: str, trace_id: str) -> QueryPlan:
        if not isinstance(raw, str) or not raw.strip():
            raise PlannerValidationError("empty planner response")
        payload = self._extract_json(raw)
        if not isinstance(payload, Mapping):
            raise PlannerValidationError("planner response must be a JSON object")
        unknown = set(payload) - _ALLOWED_RESPONSE_KEYS
        if unknown:
            raise PlannerValidationError(f"unknown planner fields: {sorted(unknown)}")
        try:
            intent = payload["intent"]
            backends = tuple(payload["backends"])
            raw_queries = payload["queries"]
            raw_filters = payload.get("filters", {})
            mode = payload["retrieval_mode"]
            limit = payload["limit"]
        except KeyError as error:
            raise PlannerValidationError(f"missing planner field: {error.args[0]}") from error
        if not isinstance(intent, str) or not isinstance(backends, (list, tuple)):
            raise PlannerValidationError("intent/backends have invalid types")
        if not isinstance(raw_queries, list) or not raw_queries:
            raise PlannerValidationError("queries must be a non-empty list")
        if not isinstance(raw_filters, Mapping):
            raise PlannerValidationError("filters must be an object")
        if set(raw_filters) - FILTER_KEYS:
            raise PlannerValidationError("planner invented an unsupported filter")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise PlannerValidationError("limit must be an integer")

        filters = self._validated_filters(raw_filters, original_query)
        queries = self._validated_queries(raw_queries, original_query, trace_id)
        plan = QueryPlan(
            original_query=original_query,
            intent=intent,
            backends=backends,
            queries=queries,
            filters=filters,
            retrieval_mode=mode,
            limit=limit,
            trace_id=trace_id,
            planner_model=self.model,
            planner_provider=self.provider,
        )
        plan.validate()
        return plan

    @staticmethod
    def _extract_json(raw: str) -> Any:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise PlannerValidationError("planner response was not valid JSON")
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as error:
                raise PlannerValidationError(f"planner response was not valid JSON: {error}") from error

    @staticmethod
    def _validated_queries(raw_queries: list[Any], original_query: str, trace_id: str) -> tuple[PlannedQuery, ...]:
        result: list[PlannedQuery] = []
        seen: set[str] = set()
        for item in raw_queries[:4]:
            if not isinstance(item, Mapping):
                raise PlannerValidationError("each planned query must be an object")
            text = item.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > _MAX_REWRITTEN_QUERY:
                raise PlannerValidationError("planned query text is empty or too long")
            normalized = text.strip()
            if normalized.casefold() in seen:
                continue
            if "viking://" in normalized and not normalized.startswith(CORNELL_NAMESPACE):
                raise PlannerValidationError("planner produced a foreign namespace URI")
            seen.add(normalized.casefold())
            result.append(
                PlannedQuery(
                    text=normalized,
                    original_query=original_query,
                    trace_id=trace_id,
                    role=str(item.get("role", "retrieval")),
                    backend=item.get("backend"),
                )
            )
        if not result:
            raise PlannerValidationError("all planned queries were empty or duplicates")
        return tuple(result)

    @staticmethod
    def _validated_filters(raw: Mapping[str, Any], original_query: str) -> QueryFilters:
        course = raw.get("course")
        if course is not None:
            if not isinstance(course, str) or not _COURSE_RE.fullmatch(course.strip()):
                raise PlannerValidationError("invalid course filter")
            if course.replace(" ", "").casefold() not in original_query.replace(" ", "").casefold():
                raise PlannerValidationError("planner invented a course filter")
        lecture = raw.get("lecture")
        if lecture is not None:
            if not isinstance(lecture, int) or isinstance(lecture, bool):
                raise PlannerValidationError("lecture filter must be an integer")
            match = _LECTURE_RE.search(original_query)
            if not match or int(match.group(1)) != lecture:
                raise PlannerValidationError("planner invented a lecture filter")
        source_type = raw.get("source_type")
        filters = QueryFilters(
            course=course.strip() if isinstance(course, str) else course,
            lecture=lecture,
            source_type=source_type,
            semester=raw.get("semester"),
            date=raw.get("date"),
        )
        filters.validate()
        return filters

    def _fallback(self, query: str, trace_id: str) -> QueryPlan:
        plan = QueryPlan(
            original_query=query,
            intent="document_lookup",
            backends=("openviking",),
            queries=(PlannedQuery(query, query, trace_id),),
            filters=QueryFilters(),
            retrieval_mode="hybrid_rerank",
            limit=self.default_limit,
            trace_id=trace_id,
            planner_model=self.model,
            planner_provider=self.provider,
            status="fallback",
        )
        plan.validate()
        return plan


__all__ = ["PlannerLLM", "PlannerValidationError", "QueryPlanner"]
