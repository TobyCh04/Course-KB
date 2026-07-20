# Cornell Knowledge Base — Project Plan

**Status:** APPROVED
**Created:** 2026-07-09
**Location:** `~/hermes_related/Cornell_KB/`

## Current Status — 2026-07-19

- **Production OpenViking:** verified healthy on mini-PC port `1934`, using `bge-small-en-v1.5-f16` embedding index and DeepSeek V4 Flash VLM. Production config unchanged.
- **Cornell ingestion safety:** implemented and tested. Manifest covers 32 resources: 17 reference + 15 TEST PDFs.
- **Retrieval foundation — complete:** BM25 + dense RRF hybrid is the default production retrieval path; reranker installed but deferred. Planner emits one compact keyword-only query; formula/definition/explanation wording stays with the original query for the main model.
- **Hindsight metadata filtering — complete (`8e93df3`):** course, lecture, source type, source scope, semester, and date filters propagated through the full ingestion + recall chain. Namespaced tags generated during ingest, applied via `tags_match="all_strict"` for deterministic filtered recall. Old untagged memories remain retrievable via unfiltered recall.
- **Planner keyword refinement — complete (`57b6fc6`):** expanded stopword set from 26 to ~70 tokens covering conversational verbs, pronouns, question words, auxiliary verbs, and filler. Queries now extract purely technical domain terms. RRF-only benchmark stable at 70% read hit@5 / 60% top-1 context hit.
- **Textbook processor — complete (`1d20f44`):** 6-stage pipeline (overview → 3 parallel extractors → triple verification → OpenViking index prep → cross-reference → Hindsight retain). Default model: DeepSeek V4 Pro via CommandCode. Text-only, operates on pre-extracted PDF text. Tested on real control-design PDF: 11 verified concepts, 100% findable.
- **Next:** homework/exam processor (Phase 2 step 11), then `cornell-kb` Hermes skill (Phase 3 step 12).

## Session Working Framework

All Cornell-KB implementation sessions follow [`LUNA_DS_WORKING_FRAMEWORK.md`](LUNA_DS_WORKING_FRAMEWORK.md): GPT-5.6 Luna owns architecture, planning, review, and integration; DeepSeek V4 Pro through CommandCode handles bounded implementation and tests through Hermes delegation. The project-root [`AGENTS.md`](AGENTS.md) makes this contract visible to project-root Hermes/Coding Agent sessions. Runtime query planning remains in the active Hermes turn and must not create a second model connection.

## Overview

An AI-powered personal knowledge base for Cornell MEng coursework. Ingests lecture slides, audio transcripts, textbooks, homework, and exams through the laptop's OCR/Whisper pipeline. Uses OpenViking as the source-grounded document retrieval backend and Hindsight as the complementary personal, temporal, and graph-memory layer. Generates structured notes, enables natural language search across all material, and supports active recall through quizzing. Integrates with Obsidian for browsable notes and Hermes for conversational access.

## Media Pipeline Commands and Performance Options

Run commands from the project root. The original command forms remain valid:

```powershell
python transcribe.py transcribe lecture.mp3
python transcribe.py transcribe study_group.mp3 --engine moss
python transcribe.py ocr lecture_notes.pdf
python transcribe.py vision diagram.png --prompt "explain this"
python scripts/diagrams.py slides.pdf --course "SYSEN 5100" --lecture 1
```

### Transcription and OCR configuration

- **Whisper:** use `--device` and `--compute-type` to override CUDA defaults, e.g.
  `python transcribe.py transcribe lecture.mp3 --device cpu --compute-type int8`.
  Within a long-lived Python process, identical Whisper model/device/compute settings
  reuse the loaded model; pass `--no-model-cache` to force a fresh load.
  Environment equivalents are `CORNELL_KB_WHISPER_DEVICE` and
  `CORNELL_KB_WHISPER_COMPUTE_TYPE`.
- **MOSS:** `--engine moss --moss-model <id> --moss-device <preference>` selects a
  diarization runtime; defaults remain `OpenMOSS-Team/MOSS-Transcribe-Diarize` and
  `auto`. `CORNELL_KB_MOSS_MODEL` and `CORNELL_KB_MOSS_DEVICE` provide the same
  configuration, and cached runtimes are reused in-process unless disabled.
- **Scanned PDFs:** scanned pages render at **150 DPI** by default. Override only
  when required with `--dpi <value>`. GLM-OCR remains primary and Qwen3-VL remains
  the fallback: `--engine glm-ocr --fallback-engine qwen3-vl:8b`.
- **Ollama endpoint:** OCR and `vision` accept `--ollama-url URL`; set
  `CORNELL_KB_OLLAMA_URL` for a default endpoint. This makes local and remote
  deployments explicit without changing scripts.

Diagram extraction now asks the vision model for both the category and detailed
structured description in one request. It represents scanned pages by one full-page
render, removes duplicate extracted image bytes, and uses a unique temporary directory
per run that is removed even if processing fails. OCR rendering has the same unique,
cleaned-up temporary-directory behavior, so concurrent/repeated runs do not share
`page_N.png` filenames.

## Deterministic lexical-index rebuild

`data/lexical_index.json` is generated and ignored by Git. Rebuild it from the authoritative manifest with:

```powershell
python scripts/source_manifest.py rebuild-index --manifest config/source_manifest.json --root . --index-path data/lexical_index.json
```

The command validates all source hashes and metadata first, then rebuilds the index from the curated text resources and manifest-linked extracted PDF text. The PDF files remain the OpenViking source artifacts; their extracted JSON is used only for BM25 indexing.

## Phases

### Phase 1: Core Infrastructure
1. **Whisper Transcription Pipeline** — Install Whisper on RTX 4080 laptop, test with sample lecture audio, create a script that takes audio file → outputs clean transcript with timestamps
2. **Document Extraction Pipeline** — PDF text extraction (slides, textbooks, homework) using pymupdf, handle formulas/diagrams, output structured markdown
3. **Hindsight Integration** — Set up retain/recall/reflect with course metadata schema (course, lecture#, source_type, topic, date), test ingestion and retrieval for personal/temporal/graph memory

### Phase 2: Knowledge Processing and Retrieval Backend
4. **Lecture Note Generator** — Takes transcript + slide PDF → generates structured lecture notes (key concepts, formulas, examples, action items)
5. **OpenViking Cornell Backend** — Safe curated adapter, source search/read/trace CLI, and ingestion safety complete; laptop orchestration remains separately deferred.
6. **Primary English Embedding Upgrade** — EmbeddingGemma A/B experiment complete but not promoted; BGE-small remains the production baseline while remote latency and held-out evaluation remain open.
7. **Reranking Layer** — ✅ Complete: cross-encoder reranking with persistent `bge-reranker-base` server and dense fallback.
8. **Lexical/Hybrid Retrieval** — ✅ Complete: BM25 lexical retrieval plus dense RRF fusion, canonical URI deduplication, and rebuilt metadata-aware lexical index.
9. **LLM Query Layer** — ✅ Complete: validated planner contracts, deterministic fallback, lexical/semantic role routing, one shared hybrid execution, provenance, readable-source filtering, query-focused reranker context, and source-read verification.
10. **Textbook Processor** — ✅ Complete (`1d20f44`): 6-stage pipeline extracts concepts, formulas, examples from textbooks → prepares OpenViking resources with structured metadata tags → retains learning memories in Hindsight. Default model: DeepSeek V4 Pro via CommandCode. 3 parallel extractors (concepts/formulas/examples), triple verification (source-anchored, testable, non-trivial), LaTeX-aware JSON parser. Tested on real control-design PDF: 11 verified concepts, 100% retrieval findability.
11. **Homework/Exam Processor** — Extracts problem statements, solution patterns, common mistakes → indexes source content in OpenViking and retains review memories in Hindsight

### Phase 3: Hermes Skill
12. **`cornell-kb` Skill** — Commands: `/ingest`, `/review`, `/quiz`, `/search`, `/connect`
13. **Teach Skill Integration** — Pull from OpenViking and Hindsight for context-aware quizzing, track weak areas

### Phase 4: Obsidian Layer
14. **Vault Structure** — `Cornell/` folder with per-course subfolders, lecture note templates, cross-reference wikilinks
15. **Auto-Sync** — OpenViking source references and Hindsight recall results export as Obsidian notes, backlinks auto-generated

### Phase 5: Exam and Review
16. **Comprehensive Review Generator** — Per-course review from all stored material
17. **Spaced Repetition System** — Track reviewed topics, surface weak areas before exams

### Phase 6: Pipeline Operations and Evaluation
18. **Laptop Pipeline Orchestration** — Route OCR, Whisper, semantic extraction, embedding, and indexing through the laptop because the media models already run there
19. **Retrieval Evaluation and Promotion** — Expand the grounded benchmark with ambiguous, formula-heavy, multi-source, temporal, and multi-hop questions; compare Recall@1/5, MRR, source traceability, context quality, latency, and resource use before promoting a production configuration

## Pipeline Flow

```
Lecture slides (PDF) ──┐
Lecture audio ─────────┤
Textbook chapters ─────┼──→ Laptop Extract/OCR/Whisper ──→ OpenViking Resources
Homework/exams ────────┘                    │                     ↓
                                           │              Source-grounded read/search
                                           ▼                     │
                                    Hindsight Retain ───────┐    │
                              (personal/temporal/graph)    │    │
                                                            ▼    ▼
                                             Hermes `cornell-kb` Backend
                                                            ↓
                                           Obsidian Notes / Teach / Quiz
```

## Next Steps

- [ ] Detailed plan for Phase 1
- [x] Detailed plan for Phase 2 (steps 6-9: OpenViking retrieval) — [step6_openviking_plan.md](step6_openviking_plan.md)
- [ ] Detailed plan for Phase 3
- [ ] Detailed plan for Phase 4
- [ ] Detailed plan for Phase 5
- [x] Detailed OpenViking retrieval plan: [backend, embedding upgrade, reranking, hybrid retrieval, and LLM query layer](step6_openviking_plan.md)
- [ ] Detailed plan for Phase 6 pipeline operations and retrieval evaluation
