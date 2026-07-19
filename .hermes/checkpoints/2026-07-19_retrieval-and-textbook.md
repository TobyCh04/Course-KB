# Cornell KB — Checkpoint 2026-07-19 (Retrieval & Textbook Processor)

## Commits this session

| Commit | Description |
|--------|------------|
| `1d20f44` | `feat(cornell-kb): textbook processor with 6-stage extraction pipeline` |
| `57b6fc6` | `refine(cornell-kb): expand planner keyword stopword coverage` |
| `8e93df3` | `feat(cornell-kb): apply metadata filters to hindsight` |
| `424228d` | prior — `feat(cornell-kb): make lexical index reproducible` |

## Retrieval backend (production)

- **Strategy:** hybrid BM25 + dense RRF only (no reranker in production).
- **Benchmark:** 70% read hit@5, 60% top-1 context hit, 217ms mean latency.
- **Reranker:** installed but deferred. Source-aware reranker improves hit@5 to 80% but 31× slower; needs larger corpus to calibrate.
- **Planner:** emits one compact keyword-only query with ~70 stopwords filtering conversational language → pure technical terms.
- **Hindsight filters:** `tags_match="all_strict"` with namespaced tags (`scope:course`, `course:…`, `lecture:…`, `source-type:…`, `semester:…`, `date:…`). Old memories safe — only excluded from filtered queries.

## Textbook processor (new, `1d20f44`)

- **File:** `scripts/textbook_processor.py` (850 lines)
- **Pipeline:** 6 stages — overview → 3 parallel extractors → triple verify → OpenViking prep → cross-ref → Hindsight retain.
- **Model:** DeepSeek V4 Pro via CommandCode (`https://api.commandcode.ai/provider/v1/chat/completions`).
- **Key:** auto-loaded from `~/.hermes/config.yaml` → `custom_providers[commandcode].api_key`.
- **Extractors:** concepts, formulas, examples (3 workers, not 5).
- **Verification:** V1 source-anchored, V2 testable, V3 non-trivial.
- **Parser:** LaTeX-aware (`\omega`, `\frac` backslash escaping).
- **Tested:** Control Design Part I PDF (14.5K chars) → 11 verified concepts, 100% findable.

## Usage

```bash
PYTHONPATH=. python scripts/textbook_processor.py process "textbook.pdf" \
  --course "SYSEN 6800" --chapter 1 --dry-run

PYTHONPATH=. python scripts/textbook_processor.py process "textbook.pdf" \
  --course "SYSEN 6800" --chapter 1  # full ingest (Hindsight)
```

## Test suite

- **119 passed** in 1.04s (`pytest -q`).
- Test files: `tests/test_query_planner.py` (25), `tests/test_ingest.py` (~44), others (~50).

## Next steps

1. **Homework/Exam Processor** (Phase 2 step 11) — problem extraction, solution patterns, `scope:assessment` tags.
2. **`cornell-kb` Hermes skill** (Phase 3 step 12) — `/ingest`, `/search`, `/review`, `/quiz`, `/connect`.
3. **Reranker recalibration** — only after real course material is available.
