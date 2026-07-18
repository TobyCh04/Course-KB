# Step 6.6 — LLM-Enhanced Query Layer Implementation Plan

> For Hermes: implement this plan task-by-task with strict TDD and independent review after each implementation slice.

**Goal:** Add a safe, traceable LLM query-planning layer that improves vague and multi-part Cornell study questions while preserving deterministic retrieval fallback and source provenance.

**Architecture:** The planner sits above the existing OpenViking dense search, BM25/RRF hybrid retrieval, reranker, and Hindsight clients. It converts one user query into a validated `QueryPlan`; the executor runs that plan; a `QueryTrace` records what was planned and what actually happened. The LLM may propose intent, rewrites, filters, and backend selection, but validation—not the LLM—controls namespaces, filters, limits, and fallback behavior.

**Current state:** Step 6.4 reranking and Step 6.5 hybrid retrieval are complete. Step 6.6 has not been implemented. Preflight hardening is being recorded separately: strict Cornell namespace validation and lexical-index metadata derivation are in progress. Production OpenViking remains unchanged on the existing BGE-small baseline.

---

## 1. Concepts and contracts

### 1.1 Query plan — intended retrieval strategy

A `QueryPlan` is the validated result of planning one user query. It should contain:

- `original_query: str` — exact user wording, preserved for final answer phrasing
- `intent: str` — one of the supported intent values
- `backends: list[str]` — `openviking`, `hindsight`, or both
- `queries: list[PlannedQuery]` — one or more rewritten retrieval queries
- `filters: QueryFilters` — only filters explicitly supported by the user query or trusted caller context
- `retrieval_mode: str` — `dense`, `hybrid`, or `hybrid_rerank`
- `limit: int` — validated and bounded before execution
- `trace_id: str` — non-secret identifier linking every generated query to the original request

Supported intents:

- `document_lookup`
- `personal_memory`
- `temporal_event`
- `entity_relationship`
- `formula_exact_term`
- `multi_source_synthesis`

Each `PlannedQuery` should contain:

- `text`
- `original_query`
- `trace_id`
- `reason` or `role`
- optional query-local backend/mode override

### 1.2 Query trace — actual execution record

A `QueryTrace` is not the plan itself. It records execution facts:

- original query and trace ID
- validated plan summary
- generated queries and their statuses
- selected backend for each query
- filters actually applied
- dense, lexical, and reranker timings
- result counts
- final source URIs
- fallback activation and reason
- sanitized errors
- completion status

Never store API keys, Authorization headers, raw credentials, or unrelated prompt secrets in the trace.

---

## 2. Routing behavior

| Query type | Default backend | Retrieval behavior |
|---|---|---|
| Document/source lookup | OpenViking | Dense or hybrid search, optionally reranked |
| Formula/exact term | OpenViking | Hybrid BM25 + dense; preserve symbols and course codes |
| Personal memory | Hindsight | Recall only; no OpenViking dependency |
| Temporal event | Hindsight | Temporal/personal recall |
| Entity/relationship | Hindsight | Graph/entity-oriented recall |
| Multi-source synthesis | OpenViking, possibly Hindsight | Search multiple source queries and merge provenance |
| Mixed source + personal question | Both | Execute independently, label backend provenance |

The planner must not fabricate a course, lecture, semester, date, or source constraint. If the user query does not explicitly provide a filter, the validated plan must leave that filter empty unless trusted caller context supplies it.

---

## 3. LLM boundary and deterministic fallback

Create `scripts/query_planner.py` with an injectable LLM callable/client. Do not call paid APIs from unit tests.

The planner should:

1. Validate that the original query is non-empty.
2. Build a prompt requesting one JSON object matching the planner schema.
3. Call the injected LLM with a bounded timeout.
4. Parse JSON defensively, including fenced or prose-wrapped JSON only if the extracted object validates.
5. Reject unknown intents, backends, filters, namespaces, invalid limits, empty queries, and invented filters.
6. Normalize duplicate rewritten queries while preserving original-query links.
7. Return a deterministic fallback plan if the LLM fails, times out, returns malformed JSON, or produces unsafe output.

Fallback plan:

- `intent = document_lookup` unless trusted caller context says otherwise
- `backends = [openviking]`
- one query equal to the exact original query
- no inferred filters
- bounded default limit
- default retrieval mode `hybrid_rerank` if available, otherwise `hybrid`
- trace status `fallback`

The fallback must never silently convert an LLM or backend failure into an empty successful result.

---

## 4. Backend and metadata prerequisites

### 4.1 OpenViking backend

Extend `scripts/openviking_backend.py` only after tests define the behavior:

- accept validated filter parameters without allowing arbitrary client kwargs
- pass supported OpenViking SDK search filters through explicitly
- preserve namespace locking for the root and all child URIs
- normalize and validate the SDK response shape
- distinguish malformed/error responses from valid zero-result responses
- keep limits bounded with named constants

The namespace check must accept exactly `viking://resources/cornell-kb` and descendants beginning with `viking://resources/cornell-kb/`; prefix lookalikes are forbidden.

### 4.2 Lexical metadata

`lexical_index.py` must retain uniform JSON-derived metadata such as `course`, `lecture`, `source_type`, `semester`, and `date` when every record in a source file agrees. Semantic metadata must not change the deterministic URI identity used for dense/lexical RRF alignment.

The rebuilt lexical index must be verified after any metadata schema change.

### 4.3 Hybrid retrieval

Extend hybrid retrieval to support multiple planned query lists without pairwise order-dependent fusion. Provenance entries must include:

- backend/source (`dense` or `lexical`)
- generated query
- original query
- rank and score
- canonical URI

Reject or discard non-Cornell lexical URIs before fusion. Preserve the original query in the outer result and trace.

### 4.4 Reranker fallback

When reranking fails, fallback ordering must use `fused_score` for hybrid candidates and `score` for dense candidates. Do not accidentally return fewer results than requested when `top_k` and `rerank_top` differ; define and test the intended behavior.

---

## 5. Files

### Create

- `Cornell_KB/scripts/query_planner.py`
- `Cornell_KB/tests/test_query_planner.py`

### Modify

- `Cornell_KB/scripts/openviking_backend.py`
- `Cornell_KB/scripts/common_client.py` if the planner needs a small reusable structured-LLM helper
- `Cornell_KB/scripts/hybrid_retrieval.py`
- `Cornell_KB/scripts/search.py`
- `Cornell_KB/scripts/lexical_index.py`
- `Cornell_KB/scripts/reranker.py`
- `Cornell_KB/tests/test_openviking_backend.py`
- `Cornell_KB/tests/test_hybrid_retrieval.py`
- `Cornell_KB/tests/test_search_cli.py`
- `Cornell_KB/tests/test_common_client.py`

Do not modify production OpenViking configuration or re-index production as part of Step 6.6 implementation.

---

## 6. TDD implementation sequence

### Task 1: Lock down namespace and response contracts

- Add tests for search rejection of foreign and prefix-collision target URIs.
- Add tests for valid empty response versus malformed response shape.
- Implement the smallest backend normalization/validation change.
- Run the targeted tests, then the full suite.

### Task 2: Finish lexical metadata and filter matching

- Add tests for JSON-derived course/lecture/source metadata.
- Add tests proving inferred metadata does not alter URI alignment.
- Add filter matching tests for exact course, lecture, and source type.
- Rebuild `data/lexical_index.json` and verify its manifest.

### Task 3: Define and test planner models

- Add `QueryFilters`, `PlannedQuery`, `QueryPlan`, and `QueryTrace`.
- Validate enums, limits, query text, filters, namespace, and trace IDs.
- Test duplicate query normalization and rejection of unknown fields/unsafe values.

### Task 4: Implement planner fallback

- Write failing tests for LLM timeout, exception, malformed JSON, empty output, and hallucinated filters.
- Implement injectable LLM invocation and deterministic original-query fallback.
- Verify no network or paid API is used by tests.

### Task 5: Implement intent routing

- Test document → OpenViking only.
- Test memory/temporal/entity → Hindsight only.
- Test mixed questions → both backends.
- Test formula/exact-term → hybrid OpenViking mode.

### Task 6: Integrate multi-query execution and provenance

- Add N-list fusion tests.
- Ensure every generated query retains `original_query` and `trace_id`.
- Record per-query backend, latency, result count, and final source URI.
- Test partial query failure without discarding successful results.

### Task 7: Integrate CLI and trace output

- Add planner-aware search/trace entry points.
- Preserve existing direct `search`, `source`, `trace`, `hybrid`, and `hybrid-trace` behavior.
- Add planner information to trace output without exposing secrets.

### Task 8: Independent review and regression verification

- Run static checks and the complete offline test suite.
- Review all new code with a fresh subagent.
- Run only an explicitly authorized live smoke test against non-production or read-only endpoints.
- Do not promote models, rebuild production OpenViking, or commit unless separately requested.

---

## 7. Required tests

At minimum:

- planner falls back on timeout
- planner falls back on exception
- planner falls back on malformed JSON
- planner never invents course/source filters
- planner extracts only explicit filters
- document intent routes to OpenViking only
- personal-memory intent routes to Hindsight only
- mixed intent routes to both
- every generated query links to the original query and trace ID
- trace contains rewrites, backends, timings, and source URIs but no secrets
- foreign target URI is rejected by both search and read
- malformed OpenViking response is not treated as empty results
- dense-empty and dense-error paths are distinguishable
- lexical metadata survives serialization
- filter matching applies consistently to lexical candidates
- multi-query RRF is deterministic and preserves query provenance
- reranker fallback uses the correct score field
- all limits and worker counts are bounded

Project verification command:

`uv run --with pytest -- python -m pytest -q`

---

## 8. Acceptance criteria

Step 6.6 is complete only when:

- vague questions produce useful validated rewrites
- exact formulas/course codes remain intact
- filters are explicit, validated, and applied consistently
- OpenViking/Hindsight routing follows intent
- planner failure falls back to the original query deterministically
- every result is traceable to its source URI and original query
- malformed backend responses are surfaced as failures, not empty successes
- all tests are offline, deterministic, and passing
- production OpenViking remains untouched
- the plan, README, operational checkpoint, dashboard status, and `cornell-kb` skill all agree on the current state
