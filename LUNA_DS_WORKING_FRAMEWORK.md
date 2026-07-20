# Cornell-KB Luna → DeepSeek V4 Pro Working Framework

**Status:** Active project operating contract
**Project:** `C:/Users/TobyC/hermes_related/Cornell_KB/`
**Primary model:** GPT-5.6 Luna
**Implementation model:** `deepseek/deepseek-v4-pro` through CommandCode
**Delegation provider:** `custom:commandcode`
**Delegation concurrency:** up to 3 children; max spawn depth 1

## 1. Purpose

This document defines how Cornell-KB is designed, implemented, tested, and reviewed across sessions.

The central operating model is:

> **Luna is the staff engineer and architecture authority. DeepSeek V4 Pro is the implementation team. Deterministic tests, source-read benchmarks, and provenance checks are the final authority.**

Every Cornell-KB coding session must read this document before planning or changing code. The framework is deliberately separate from the volatile project status in `README.md` and `STATUS.md`; read those files as well to determine the current milestone.

## 2. Non-negotiable model roles

### Luna — staff engineer / integrator

Luna owns:

- Understanding the current architecture and project state
- Choosing the implementation boundary
- Breaking work into independently verifiable tasks
- Defining interfaces, schemas, invariants, and acceptance criteria
- Deciding whether tasks may run in parallel
- Reviewing DeepSeek outputs and actual diffs
- Resolving disagreements between implementation and project contracts
- Approving milestone integration after tests and benchmarks pass

Luna should not spend its quota writing routine boilerplate when DeepSeek can implement it safely.

### DeepSeek V4 Pro — bounded implementation worker

DeepSeek owns:

- Focused code changes with explicit file scope
- Unit and integration tests for the changed behavior
- Mechanical refactors with clear invariants
- Documentation and fixtures
- Running the requested verification commands
- Returning concrete artifacts and evidence, not a narrative claim of success

DeepSeek must not silently redesign architecture, change production defaults, modify unrelated files, or declare success without running the requested checks.

### Deterministic tools — final authority

Model claims are not verification. Prefer, in order:

1. Existing tests and new focused tests
2. Syntax/import/CLI checks
3. Source-manifest/hash validation
4. Live OpenViking health and source-read checks
5. Retrieval benchmarks with held-out queries
6. Actual diffs and file-scope checks
7. Luna review of the evidence

## 3. Session entry protocol

At the start of every Cornell-KB implementation or maintenance session, Luna must:

1. Confirm the working directory is the Cornell-KB project root.
2. Read this framework.
3. Read `README.md` and the latest relevant plan/status file, especially `step6_openviking_plan.md` and `openviking/STATUS.md` when retrieval is involved.
4. Inspect `git status --short --branch` and recent relevant commits.
5. Identify the current milestone and its acceptance gate. Do not infer progress from an old conversation summary alone.
6. Separate generated artifacts, test fixtures, and unrelated files from the stable source set.
7. Write a short internal implementation plan before delegating.
8. Delegate only after the task has a bounded scope and a verification command.

If the project root, source status, or production boundary is unclear, stop and inspect before editing.

## 4. Standard implementation loop

Use this loop for every non-trivial feature:

### Phase A — Luna plans

Luna produces:

- Goal and non-goals
- Current architecture touchpoints
- Files allowed to change
- Interfaces and data contracts
- Invariants that must remain true
- Acceptance tests and commands
- Risks and rollback point
- Whether work is parallel-safe

### Phase B — DeepSeek implements

Each child receives a self-contained task packet and modifies only its assigned scope.

### Phase C — Deterministic verification

Run local checks before asking Luna to review. Include test output and the actual diff in the review packet.

### Phase D — Luna reviews

Luna classifies findings as:

- **Blocker:** cannot integrate
- **Major:** behavior, contract, provenance, or safety risk
- **Minor:** localized quality issue that should be fixed if practical
- **Acceptable:** intentional tradeoff with evidence

For every blocker or major issue, Luna must identify the file, relevant symbol/line, reason, and smallest safe fix.

### Phase E — DeepSeek fixes

DeepSeek applies concrete fixes and reruns the failed checks. Do not ask Luna to rewrite the entire implementation unless the architecture itself is wrong.

### Phase F — Luna integrates

Luna performs one milestone gate covering requirements, architecture, source traceability, regression risk, tests, and silent behavior changes.

## 5. Delegation rules

Hermes delegation is configured for:

- Provider: `custom:commandcode`
- Model: `deepseek/deepseek-v4-pro`
- Max concurrent children: 3
- Max spawn depth: 1
- Orchestrator mode: enabled
- MCP tool inheritance: enabled

Use subagents as much as is practical, but do not parallelize merely to create activity.

### Parallel-safe work

Parallelize only when tasks have disjoint write scopes or are read-only. Suitable examples:

- Extraction code and independent test fixtures
- Retrieval benchmark analysis and documentation updates
- Separate parser modules with separate test files
- Read-only audits of different subsystems

### Serialize these tasks

Do not run parallel writers on:

- The same Python module
- Shared configuration files
- The production manifest or lexical index
- OpenViking migration/cleanup operations
- Hindsight tag/schema migrations
- The final integration branch

Subagents have separate conversations and terminals, but project files can still be shared. Assume concurrent writes can conflict unless proven otherwise.

### Task sizing

A good DeepSeek task usually changes one focused behavior in one to four source files and includes its tests. Split larger work by contract or subsystem, not by arbitrary line count.

## 6. DeepSeek task packet

Every delegated coding task should include this structure:

### Goal

One precise outcome.

### Context

Relevant architecture, current behavior, and why the change is needed.

### Allowed scope

Exact files/directories the child may modify.

### Forbidden scope

Files, services, production workspaces, and behaviors that must not be changed.

### Contract

Inputs, outputs, schemas, error behavior, provenance, and compatibility requirements.

### Acceptance criteria

Observable conditions that must be true after the change.

### Verification

Exact commands to run, for example:

- `python -m pytest -q tests/test_specific.py`
- `python -m py_compile scripts/module.py`
- `python scripts/source_manifest.py validate --manifest config/source_manifest.json --root .`
- `git diff --check`
- A named live read-only OpenViking query when explicitly authorized

### Completion report

The child must return:

- Files changed
- Tests/commands run
- Actual results
- Known limitations
- Any follow-up needed

A child saying "done" without this evidence is not complete.

## 7. Cornell-KB architecture invariants

### Source-grounded retrieval

- OpenViking is the source-grounded document backend.
- The production namespace is exactly `viking://resources/cornell-kb` and child URIs under it.
- Every source-grounded answer must preserve the source URI and provenance.
- Never accept unconstrained LLM-generated URIs, limits, or namespaces.
- Validate the namespace before fusion and before source reads.

### Hindsight separation

- Hindsight is the complementary personal, temporal, graph, and learning-history layer.
- Do not use Hindsight as a replacement for canonical source retrieval.
- Course facts use the `cornell-kb` scope and namespaced metadata tags.
- Personal mastery, review history, temporal relationships, and learning state belong in Hindsight rather than bulk OpenViking source content.

### Retrieval default

- Production default is hybrid BM25 + dense RRF without reranking.
- The reranker is installed and documented but remains opt-in until representative course data supports promotion.
- Do not change the production retrieval default based on a small or unequal benchmark.
- Retrieval experiments require identical corpus, chunking, metadata, query set, and source-read scoring between branches.

### Query planner boundary

For a normal Cornell user question, the active Hermes main model produces the validated query plan inside the current turn. The planner is not a second agent.

Do not use `delegate_task`, `hermes chat`, a new OpenAI client, or a separate model connection for runtime query planning. The planner must:

- Preserve the original query
- Produce a validated intent/backend/filter/retrieval plan
- Use safe allowlisted filters
- Retry once on malformed or invalid output
- Surface planner failure and deterministic fallback to the user
- Preserve a sanitized query trace with source URIs and errors

This rule applies to runtime retrieval. It does not prevent delegating repository implementation work to DeepSeek.

### Manifest and ingestion gate

Before real course ingestion:

1. Preserve a rollback checkpoint and inventory.
2. Validate the authoritative manifest.
3. Require full source hashes and source types.
4. Omit `lecture` metadata when a source spans multiple lectures or is not lecture material.
5. Run the manifest dry run.
6. Rebuild the generated lexical index from the manifest.
7. Verify test/synthetic resources are absent from the target workspace.
8. Verify queue errors, missing vectors, namespace boundaries, and source-read evidence.

Never treat a successful upload or healthy service as proof that ingestion completed correctly.

### Media and text boundaries

- Whisper/MOSS, pymupdf, GLM-OCR, and Qwen3-VL handle media preprocessing.
- DeepSeek V4 Pro is the default text implementation/synthesis model; it is not the OCR/vision engine.
- Fact-checking must verify against model knowledge, using OCR/transcript material as secondary evidence; it must not blindly reproduce OCR errors.
- Correction passes must rewrite incorrect note content in place, not merely append a warning.

## 8. Verification policy

### Offline first

Before any paid/live call:

- Run the focused tests.
- Run the relevant project test suite.
- Validate JSON/YAML/schema outputs.
- Run `git diff --check`.
- Inspect changed-file scope.
- Use fake transports/LLM callables in tests; tests must not contact paid providers.

### Live verification

A live claim requires a real live result. For OpenViking, record:

- Original query
- Validated plan
- Trace ID
- Backend URL
- Health result
- Retrieval mode
- Result count
- Source URIs
- Timings
- Fallback/error state

A valid plan followed by a connection failure is a failed live smoke test, not partial success.

### Benchmark promotion

Do not promote an embedding, reranker, blend, or retrieval policy because it looks better on one query. Require:

- Same corpus and metadata
- Held-out queries
- Recall@1/5 and MRR
- Top-1 context support
- Source traceability
- Latency and resource measurements
- Queue/error counts
- A rollback path

## 9. Luna quota and review efficiency

Luna is the main model, so every delegated workflow also consumes Luna turns for planning, synthesis, and review. Keep Luna high-leverage:

- Default to one planning gate and one final gate per milestone.
- Use an additional Luna review only for a blocker, persistent test failure, core data-contract change, retrieval regression, production indexing change, or security/persistence/migration change.
- Send Luna diffs, acceptance criteria, changed files, test output, and failing tracebacks—not the entire repository by default.
- Ask for structured findings and concise patch instructions.
- Use deterministic tools to catch easy errors before a Luna review.
- Reserve maximum reasoning for architecture and final integration; normal/high reasoning is sufficient for ordinary diff review.
- Never spend Luna quota rechecking a clean, well-tested mechanical change without a risk signal.

## 10. Git, production safety, and rollback

- Inspect status before editing.
- Preserve existing user changes.
- Keep production OpenViking and production vector workspaces protected during experiments.
- Use isolated A/B workspaces for embedding/retrieval trials.
- Do not delete or move ambiguous files; locate their owning project first.
- Do not commit, push, or publish unless the user explicitly asks.
- Before risky migrations, record a checkpoint and an inventory.
- A failed experiment must leave the production configuration and rollback path intact.

## 11. Session completion report

At the end of a Cornell-KB work session, report:

1. What Luna decided
2. Which DeepSeek tasks were dispatched
3. Files actually changed
4. Tests and live checks actually run
5. Results and evidence paths
6. Known limitations or unresolved failures
7. Whether production configuration changed
8. The next bounded milestone

Never report a subagent's self-reported success as verified success without reading the artifact or rerunning the relevant check.
