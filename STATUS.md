# Cornell-KB Project Status

**Last updated:** 2026-07-21
**Branch:** `master`
**Working tree:** clean at time of last commit; pre-semester hardening changes uncommitted

## Completed — pre-semester hardening (2026-07-21)

### Priority 1: Strict source-change rejection ✅

- `SourceHashMismatch` exception raised when same logical source is re-ingested with a different content hash.
- Idempotent skip when same logical source + same hash is re-ingested (no redundant `add_resource` call).
- `_logical_source_key()` and `_logical_source_stem()` helpers extract course/source-type/stem identity from URIs, stripping the 12-char hash-derived digest.
- Stem derivation in `resource_uri()` now includes parent-directory prefix for files in subdirectories, eliminating false collisions for same-named files (e.g. `books/lean-implementation/*/SKILL.md`).
- Check enforced in `index_file()` (per-resource gate) and propagates naturally through `ingest_manifest()`.

**Files:** `scripts/openviking_backend.py`, `scripts/source_manifest.py`, `tests/test_openviking_backend.py` (+6 tests)

### Priority 2: Reproducible preflight command ✅

- New `scripts/preflight.py` — single command, six checks:
  1. Manifest validation (paths, hashes, duplicates)
  2. Service health (OpenViking, embedding, Hindsight) — injectable for tests
  3. LLM routing (model must be `deepseek-v4-pro`, URL must be `api.deepseek.com/v1`, Flash rejected)
  4. Logical-source conflict scan (same-stem-different-hash in manifest)
  5. Dry-run URI + provenance preview for every manifest entry
  6. Git working-tree cleanliness
- All checks are injectable — tests never contact live services.
- Output: human-readable text or machine-readable JSON.
- `--no-services` and `--no-git` flags for offline mode.

**Files:** `scripts/preflight.py` (new), `tests/test_preflight.py` (new, 20 tests)

### Manifest cleanup: lean-implementation removed

- 14 lean-implementation entries removed from `config/source_manifest.json` (files preserved on disk as separate project).
- `RAW_BOOK_FILENAMES`, `CURATED_DERIVED_ROOT`, `CURATED_DERIVED_EXCLUDED_PARTS`, `CURATED_DERIVED_EXTENSIONS` removed from `openviking_backend.py`.
- `is_approved_cornell_path()` now only accepts `CURATED_SOURCE_PATHS` entries.
- `lexical_index.py` no longer scans `books/lean-implementation/` for indexing.
- Manifest: 32 → 18 entries (3 reference + 15 TEST PDFs).

**Files:** `config/source_manifest.json`, `scripts/openviking_backend.py`, `scripts/source_manifest.py`, `scripts/lexical_index.py`, `tests/test_openviking_backend.py`

## Verification

- **276 tests pass** (was 249 after Priority 5; +27 student workflow smoke tests)
- Python compilation clean
- `git diff --check` clean
- Preflight: 4/4 PASS (offline), SKILL.md conflict resolved
- E2E gate: 8/8 PASS (offline), covers first write, idempotency, hash-mismatch, provenance, read-back, Hindsight, rollback inventory, cleanup
- Media fixtures: 6/6 PASS (offline), all 6 processors produce artifacts with source_hash, extraction_engine, ingestion_timestamp, downstream_resource_status
- Recovery tooling: 22/22 PASS — structured JSONL logging, checkpoint/resume, resource inventory snapshot/diff, test cleanup (OpenViking + Hindsight), course manifest template

## Remaining pre-semester work

### Priority 3: Complete isolated end-to-end gate ✅

Check in a repeatable gate covering: first write, duplicate idempotency, provenance/source read-back, strict hash mismatch behavior, no memory linking or token explosion, isolated Hindsight retain/recall, rollback inventory, and cleanup with zero test resources remaining.

- `test_runs/e2e_gate.py` — repeatable gate with 8 sequential checks, injectable fakes
- `tests/test_e2e_gate.py` — 16 offline tests covering every gate step in isolation + full gate
- All gate steps pass with shared fake client; live mode wired for OpenViking + Hindsight
- Gate is idempotent: running twice on the same workdir passes both times

### Priority 4: Media-fixture validation ✅

Run isolated fixtures for Whisper/MOSS, pymupdf, GLM-OCR, Qwen3-VL/diagram extraction, and DeepSeek V4 Pro synthesis. Every artifact must carry source hash, extraction engine, timestamp, and downstream resource status.

- `scripts/media_artifact.py` — `ArtifactRecord` dataclass with the four required fields + `make_artifact()` factory + `validate_artifact()` checker
- `scripts/media_fixture_validation.py` — 6-fixture validation: whisper, moss, pymupdf, glm-ocr, qwen3-vl, deepseek-synthesis; all injectable
- `tests/test_media_fixture_validation.py` — 24 offline tests, all pass
- Every artifact carries: `source_hash`, `extraction_engine`, `ingestion_timestamp`, `downstream_resource_status`
- Valid engines: whisper-large-v3-turbo, moss-0.9b, pymupdf, glm-ocr, qwen3-vl:8b, deepseek-v4-pro
- Valid statuses: pending_openviking, indexed, pending_hindsight, complete, skipped, failed

### Priority 5: Recovery/checkpoint/cleanup tooling ✅

Structured ingestion logs, retry/resume checkpoints, queue/error reporting, resource inventories, test cleanup, course manifest templates.

- `scripts/ingestion_logger.py` — JSONL ingestion log (append-only) with `IngestionLogger` class; `read_logged_uris()` + `build_resume_manifest()` for checkpoint/resume
- `scripts/resource_inventory.py` — `snapshot()` pre/post ingestion, `diff()` before/after comparison, save/load as JSON
- `scripts/test_cleanup.py` — `run_cleanup()` removes test resources by URI, pattern, or manifest entry; dry-run mode; Hindsight bank cleanup
- `config/course_manifest_template.json` — starter template with 6 source types (textbook, transcript, homework, exam, slides, derived OCR)
- `tests/test_recovery_tooling.py` — 22 offline tests covering logger, checkpoint/resume, inventory snapshot/diff, cleanup, template validation

### Priority 6: Student workflow smoke tests ✅

Verify source-grounded answers, lecture explanations, quiz generation, new homework-style problems, separate answer keys, empty-retrieval behavior, and Hindsight/OpenViking scope selection.

- `tests/test_student_workflow_smoke.py` — 27 smoke tests covering all 7 verification points
- Source-grounded: search → trace → source-read pipeline verified
- Explanations: `explain_fact` with found/missing handling
- Quiz: no inline answers, deterministic with seed, empty facts handling
- Homework: practice variants, LLM-generated new problems, original wording never copied
- Answer keys: structurally separate, IDs match questions
- Empty retrieval: graceful handling of zero results across search/trace/explain/review
- Scope: `source_scope` filter correctly separates assessment from course material

### Priority 7: Course onboarding templates ✅

Naming conventions, course namespaces, Obsidian output structure.

- `docs/course-onboarding.md` — complete onboarding guide: naming conventions, URI structure, manifest rules, source-type catalog, Obsidian vault template with frontmatter spec, step-by-step checklist
- `config/course_namespaces.yaml` — authoritative registry of all 12 course codes + 2 test courses, mapping slug, OpenViking namespace, Obsidian path, semester, status
- Obsidian template: frontmatter with course/lecture/source_type/source_uri/extraction_engine/generated/tags, note structure with Key Concepts/Definitions/Diagrams/Action Items sections, source citation footer

## Deferred (not blockers for first safe course ingestion)

- Promote a larger embedding model — held-out benchmark + latency comparison required.
- Re-enable/recalibrate reranking — requires representative course material.
- Web verification/search coverage improvements.
- Replace local media models (only if verified DeepSeek multimodal API path becomes available).

## Doable before school starts (from plan files — not yet prioritized)

These are items from `step6_openviking_plan.md`, `step4_note_generator_plan.md`,
and `step3_hindsight_plan.md` that require zero real course files:

| # | Item | Plan ref | What it is |
|---|------|----------|-----------|
| D1 | **Laptop pipeline script** | 6.2 | `laptop_pipeline.py` that runs full media→ingest pipeline end-to-end on RTX 4080. Currently each step (transcribe, OCR, index) is manual. One command: audio+PDF+diagram → OpenViking resource. Needs Tailscale connectivity verified first. |
| D2 | **Expanded retrieval benchmark** | 6.3/6.8 | Add 15-20 more synthetic sources (formula-heavy, multi-source, ambiguous) to the current 10-query benchmark. Current benchmark saturated at 100% with bge-small — can't measure improvement without harder queries. |
| D3 | **Batch ingestion** | 3.6.9 | Process multiple lectures/homeworks/exams at once. `ingest_manifest()` exists but no orchestration for multi-file batch runs with logging and resume. |
| D4 | **Laptop connectivity test** | 6.2 | Verify Tailscale path from mini PC → RTX 4080 laptop (100.104.205.105) is reachable and stable for Ollama/OpenViking calls. |
| D5 | **Embedding A/B smoke test** | 6.3 | Test bge-base-en-v1.5 against bge-small on expanded benchmark. Separate workspace, no production risk. Would tell us if upgrading is worth it before courses start. |

## Gated by real course files (not doable yet)

- Production course ingestion — no lectures until late August
- Obsidian note generation from real lectures — no real transcripts
- Reranker calibration — needs representative course material
- Student workflow live testing — no real search queries
- Wikilink generation in notes — needs real note-to-note relationships
- Pipeline 6.7 (Hermes skill integration) — partially done, needs live retrieval testing

## Acceptance criteria for declaring production-ready

- Strict source-hash policy implemented and live-tested. ✅
- One isolated end-to-end gate passes all checks. ✅
- Production cleanup inventory is zero-test and reversible. ⬜
- Real course ingestion performed only from a validated manifest. ⬜
- OpenViking and Hindsight read-back checks pass. ⬜
- No unexpected memory-linking activity or internal token explosion. ⬜
- Full tests, syntax checks, and retrieval/source-read checks pass. ✅ (276 tests)
