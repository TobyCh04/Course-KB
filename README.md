# Cornell Knowledge Base — Project Plan

**Status:** APPROVED
**Created:** 2026-07-09
**Location:** `~/hermes_related/Cornell_KB/`

## Overview

An AI-powered personal knowledge base for Cornell MEng coursework. Ingests lecture slides, audio transcripts, textbooks, homework, and exams into a Hindsight-powered memory system. Generates structured notes, enables natural language search across all material, and supports active recall through quizzing. Integrates with Obsidian for browsable notes and Hermes for conversational access.

## Phases

### Phase 1: Core Infrastructure
1. **Whisper Transcription Pipeline** — Install Whisper on RTX 4080 laptop, test with sample lecture audio, create a script that takes audio file → outputs clean transcript with timestamps
2. **Document Extraction Pipeline** — PDF text extraction (slides, textbooks, homework) using pymupdf, handle formulas/diagrams, output structured markdown
3. **Hindsight Integration** — Set up retain/recall/reflect with course metadata schema (course, lecture#, source_type, topic, date), test ingestion and retrieval

### Phase 2: Knowledge Processing
4. **Lecture Note Generator** — Takes transcript + slide PDF → generates structured lecture notes (key concepts, formulas, examples, action items)
5. **Textbook Processor** — Extracts key concepts, definitions, theorems from textbook chapters → retains into Hindsight with chapter/section metadata
6. **Homework/Exam Processor** — Extracts problem statements, solution patterns, common mistakes → retains for review

### Phase 3: Hermes Skill
7. **`cornell-kb` Skill** — Commands: `/ingest`, `/review`, `/quiz`, `/search`, `/connect`
8. **Teach Skill Integration** — Pull from Hindsight for context-aware quizzing, track weak areas

### Phase 4: Obsidian Layer
9. **Vault Structure** — `Cornell/` folder with per-course subfolders, lecture note templates, cross-reference wikilinks
10. **Auto-Sync** — Hindsight recall results export as Obsidian notes, backlinks auto-generated

### Phase 5: Exam and Review
11. **Comprehensive Review Generator** — Per-course review from all stored material
12. **Spaced Repetition System** — Track reviewed topics, surface weak areas before exams

## Pipeline Flow

```
Lecture slides (PDF) ──┐
Lecture audio ─────────┤
Textbook chapters ─────┼──→ Extract ──→ Hindsight Retain ──→ Obsidian Notes
Homework/exams ────────┘         ↓
                          Hermes Queries ←── Skill Commands
                                 ↓
                          Teach/Quiz ←── Active Recall
```

## Next Steps

- [ ] Detailed plan for Phase 1
- [ ] Detailed plan for Phase 2
- [ ] Detailed plan for Phase 3
- [ ] Detailed plan for Phase 4
- [ ] Detailed plan for Phase 5
