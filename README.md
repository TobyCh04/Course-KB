# Cornell Knowledge Base — Project Plan

**Status:** APPROVED
**Created:** 2026-07-09
**Location:** `~/hermes_related/Cornell_KB/`

## Current Status — 2026-07-16

- **Production OpenViking:** healthy on mini-PC port `1934`, using `bge-small-en-v1.5-f16`.
- **Cornell ingestion safety:** implemented and tested. Audio and raw book binaries are rejected/excluded; previously indexed audio and `full_text.txt` were removed from OpenViking.
- **BGE-large A/B test:** paused before full-corpus ingestion. The `bge-large-en-v1.5` model and laptop embedding API are prepared, but the CUDA runtime launch failed and the CPU fallback was too slow. Temporary A/B services and partial workspace were stopped/removed.
- **Next resume point:** fix native CUDA launch on the RTX 4080 laptop, start the laptop embedding API, create a fresh isolated vector workspace, ingest the cleaned corpus, and run the retrieval benchmark. Do not modify production port `1934`.

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

## Phases

### Phase 1: Core Infrastructure
1. **Whisper Transcription Pipeline** — Install Whisper on RTX 4080 laptop, test with sample lecture audio, create a script that takes audio file → outputs clean transcript with timestamps
2. **Document Extraction Pipeline** — PDF text extraction (slides, textbooks, homework) using pymupdf, handle formulas/diagrams, output structured markdown
3. **Hindsight Integration** — Set up retain/recall/reflect with course metadata schema (course, lecture#, source_type, topic, date), test ingestion and retrieval for personal/temporal/graph memory

### Phase 2: Knowledge Processing and Retrieval Backend
4. **Lecture Note Generator** — Takes transcript + slide PDF → generates structured lecture notes (key concepts, formulas, examples, action items)
5. **OpenViking Cornell Backend** — Safe Cornell adapter implemented; cleanup and offline tests complete. Production integration and automatic Hermes routing remain in progress.
6. **Primary English Embedding Upgrade** — BGE-large A/B preparation complete; full indexing and benchmark paused pending CUDA runtime fix on the laptop.
7. **Reranking Layer** — Retrieve a wider candidate set with the dense embedder, then rerank the top candidates with `bge-reranker-base`, `bge-reranker-large`, or the best supported local alternative
8. **Lexical/Hybrid Retrieval** — Add BM25 or sparse retrieval for exact formulas, symbols, identifiers, acronyms, and rare technical terms; merge dense and lexical candidates before reranking
9. **LLM Query Layer** — Add LLM-assisted query rewriting, intent classification, multi-query decomposition, course/source filtering, and query expansion for ambiguous student questions
10. **Textbook Processor** — Extracts key concepts, definitions, theorems from textbook chapters → indexes source content in OpenViking and retains relevant learning memories in Hindsight
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
- [ ] Detailed plan for Phase 2
- [ ] Detailed plan for Phase 3
- [ ] Detailed plan for Phase 4
- [ ] Detailed plan for Phase 5
- [x] Detailed OpenViking retrieval plan: [backend, embedding upgrade, reranking, hybrid retrieval, and LLM query layer](step6_openviking_plan.md)
- [ ] Detailed plan for Phase 6 pipeline operations and retrieval evaluation
