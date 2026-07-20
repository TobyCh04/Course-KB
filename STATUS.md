# Cornell-KB Project Status

**Last updated:** 2026-07-20 11:14:23 -0500
**Branch:** `master`
**Latest verified commit:** `d4b4930 fix(cornell-kb): pin llm routing and source identity`
**Working tree:** clean at the time of this update

## Completed in the current hardening milestone

- Cornell text-generation paths are pinned to `deepseek-v4-pro` through the official DeepSeek API.
- OpenAI and Ollama text-generation alternatives are rejected; Flash overrides are rejected.
- OpenViking VLM configuration is `deepseek-v4-pro` through `https://api.deepseek.com/v1`.
- OpenViking client-side memory-linking trigger is disabled; server-side patched code has the defensive early return.
- Hindsight writes fail closed for the production-like `hermes-history` bank unless production authorization is explicit.
- Structured OpenViking provenance is embedded in resource arguments, including processor version, ingestion timestamp, source type, course, lecture, source hash, and safe provenance path.
- The parser-reserved `source_path` provenance collision was fixed by using `provenance_source_path`.
- Manifest-authoritative SHA-256 hashes are part of canonical resource identity; changed content at the same path cannot silently reuse the same hash-bound URI.
- Namespace and metadata protections remain covered by regression tests.
- OpenViking was restarted and is healthy on port 1934.
- Isolated live gate passed: synthetic source indexed, no `memory_linking` result appeared, source read-back succeeded, and test data was cleaned up.
- Full verification: **161 tests passed**, Python compilation passed, and `git diff --check` passed.

## Remaining work — do not ingest real course files yet

### Blocker 1: Decide and implement strict changed-content policy

Current behavior gives changed content a new hash-bound URI. This prevents aliasing and silent reuse, but it does not reject a changed source outright. If the production contract requires “same canonical source identity plus changed bytes must fail,” implement an explicit pre-write comparison:

1. Look up the legacy/path identity and its stored `source_hash`.
2. If the identity exists and the incoming hash differs, raise a clear `SourceHashMismatch` error.
3. Do not overwrite, enqueue, or create a second resource until the caller explicitly requests a versioned replacement.
4. Add tests for same hash, changed hash rejection, explicit versioning, and legacy resources without hashes.
5. Run the isolated live mismatch gate and clean all test artifacts.

Architecture decision required before implementation: choose **strict rejection** as the default, with explicit versioning/replacement as the only path for intentional revisions.

### Blocker 2: Complete the production-like isolated gate

The current live gate proves basic indexing, no memory linking, read-back, and cleanup. It still needs a single reproducible gate that also verifies:

- duplicate-run idempotency;
- source-hash/provenance read-back from the actual resource;
- zero unexpected internal LLM/token usage from resource ingestion;
- changed-content behavior under the chosen strict policy;
- Hindsight isolated-bank write, recall, and cleanup;
- zero test resources left under the Cornell namespace;
- rollback inventory before and after the gate.

Store the sanitized result under `test_runs/` and do not include secrets.

### Blocker 3: Validate all media stages separately

DeepSeek V4 Pro is the required Cornell text LLM, but it is not a replacement for local audio transcription or image/diagram understanding in the current deployment. Before course ingestion, run isolated fixtures for:

- Whisper/MOSS audio transcription;
- pymupdf digital PDF extraction;
- GLM-OCR scanned-page extraction;
- Qwen3-VL/vision diagram extraction;
- DS V4 Pro synthesis over the resulting text artifacts.

Each artifact must carry source hash, extraction engine, timestamp, and downstream resource status.

### Blocker 4: Production cleanup and rollback gate

Before any real course write:

1. Create and verify an OpenViking rollback checkpoint.
2. Export the current resource inventory.
3. Remove all synthetic/test resources from the target workspace.
4. Verify zero test fixtures remain and no canonical course resource was deleted.
5. Validate the authoritative source manifest and hashes.
6. Perform a dry-run showing exact URIs, hashes, provenance, and planned writes.
7. Obtain explicit approval for the production ingestion window.
8. Ingest only the allowlisted corpus.
9. Verify queue status, missing vectors, source read-back, provenance, and retrieval findability.
10. Preserve rollback artifacts and the sanitized ingestion report.

## Pre-semester work that is not optimization

The next work should prioritize reliability, safety, onboarding, and user workflows rather than retrieval-quality tuning. This work can be completed before real course files exist.

### Priority 1 — strict source-change protection

Change the current hash-bound URI behavior into an explicit default rejection policy:

1. Find the existing path/logical-source identity and stored `source_hash`.
2. Return success without writing when the incoming hash is identical.
3. Raise `SourceHashMismatch` when the hash differs.
4. Require an explicit version/replacement operation for intentional revisions.
5. Add unit, isolated live, and legacy-resource tests.

### Priority 2 — reproducible preflight command

Create a single pre-ingestion command that validates:

- source-manifest paths and SHA-256 hashes;
- source types and metadata;
- namespace and Hindsight-bank safety;
- OpenViking, embedding, and Hindsight health;
- exact `deepseek-v4-pro` configuration;
- dry-run URIs and provenance.

### Priority 3 — one complete isolated end-to-end gate

Check in a repeatable gate covering first write, duplicate idempotency, provenance/source read-back, strict hash mismatch behavior, no memory linking or token explosion, isolated Hindsight retain/recall, rollback inventory, and cleanup with zero test resources remaining.

### Priority 4 — representative media-fixture validation

Run isolated fixtures for Whisper/MOSS, pymupdf, GLM-OCR, Qwen3-VL/diagram extraction, and DeepSeek V4 Pro synthesis. Every artifact must carry source hash, extraction engine, timestamp, and downstream resource status.

### Priority 5 — student workflow smoke tests

Verify source-grounded answers, lecture explanations, quiz generation, new homework-style problems, separate answer keys, empty-retrieval behavior, and Hindsight/OpenViking scope selection.

### Priority 6 — recovery, observability, and onboarding

Add or verify structured ingestion logs, retry/resume checkpoints, queue/error reporting, resource inventories, test cleanup, course manifest templates, naming conventions, course namespaces, and Obsidian output structure.

### Recommended pre-semester sequence

1. Strict hash mismatch rejection.
2. Preflight command.
3. Complete isolated end-to-end gate.
4. Media-fixture validation.
5. Recovery/checkpoint/cleanup tooling.
6. Student workflow smoke tests.
7. Course onboarding templates.

These tasks are higher priority than larger embeddings, reranker calibration, retrieval-weight tuning, latency tuning, or multimodal-model replacement. Those optimizations should wait for representative course material.

## Deferred, not blockers for first safe course ingestion

- Promote a larger embedding model only after a held-out difficult-query benchmark and latency comparison.
- Re-enable or recalibrate reranking only after representative course material is available; current safe default remains hybrid BM25+dense RRF without reranking.
- Improve web verification/search coverage; current DuckDuckGo/Wikipedia fallback can be inconclusive.
- Replace local media models only if a verified DeepSeek multimodal API path becomes available and meets quality/latency requirements.

## Acceptance criteria for declaring production-ready

- Strict source-hash policy is implemented and live-tested.
- One isolated end-to-end gate passes all checks above.
- Production cleanup inventory is zero-test and reversible.
- Real course ingestion is performed only from a validated manifest.
- OpenViking and Hindsight read-back checks pass.
- No unexpected memory-linking activity or internal token explosion occurs.
- Full tests, syntax checks, and retrieval/source-read checks pass.
