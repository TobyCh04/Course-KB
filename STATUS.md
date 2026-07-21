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

- **187 tests pass** (was 161 at start of hardening milestone)
- Python compilation clean
- `git diff --check` clean
- Preflight: 4/4 PASS (offline), SKILL.md conflict resolved

## Remaining pre-semester work

### Priority 3: Complete isolated end-to-end gate ⬜

Check in a repeatable gate covering: first write, duplicate idempotency, provenance/source read-back, strict hash mismatch behavior, no memory linking or token explosion, isolated Hindsight retain/recall, rollback inventory, and cleanup with zero test resources remaining.

### Priority 4: Media-fixture validation ⬜

Run isolated fixtures for Whisper/MOSS, pymupdf, GLM-OCR, Qwen3-VL/diagram extraction, and DeepSeek V4 Pro synthesis. Every artifact must carry source hash, extraction engine, timestamp, and downstream resource status.

### Priority 5: Recovery/checkpoint/cleanup tooling ⬜

Structured ingestion logs, retry/resume checkpoints, queue/error reporting, resource inventories, test cleanup, course manifest templates.

### Priority 6: Student workflow smoke tests ⬜

Verify source-grounded answers, lecture explanations, quiz generation, new homework-style problems, separate answer keys, empty-retrieval behavior, and Hindsight/OpenViking scope selection.

### Priority 7: Course onboarding templates ⬜

Naming conventions, course namespaces, Obsidian output structure.

## Deferred (not blockers for first safe course ingestion)

- Promote a larger embedding model — held-out benchmark + latency comparison required.
- Re-enable/recalibrate reranking — requires representative course material.
- Web verification/search coverage improvements.
- Replace local media models (only if verified DeepSeek multimodal API path becomes available).

## Acceptance criteria for declaring production-ready

- Strict source-hash policy implemented and live-tested. ✅
- One isolated end-to-end gate passes all checks. ⬜
- Production cleanup inventory is zero-test and reversible. ⬜
- Real course ingestion performed only from a validated manifest. ⬜
- OpenViking and Hindsight read-back checks pass. ⬜
- No unexpected memory-linking activity or internal token explosion. ⬜
- Full tests, syntax checks, and retrieval/source-read checks pass. ✅ (187 tests)
