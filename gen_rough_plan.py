"""Generate Cornell Knowledge Base rough plan as PDF."""
from fpdf import FPDF

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_font("Deng", "", r"C:\Windows\Fonts\Deng.ttf")
pdf.add_font("Deng", "B", r"C:\Windows\Fonts\Dengb.ttf")

LM = 20
PW = 170

def nl(h=3):
    pdf.ln(h)

def title(text):
    pdf.set_font("Deng", "B", 18)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(PW, 12, text, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)

def subtitle(text):
    pdf.set_font("Deng", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(PW, 7, text, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)

def phase_header(text):
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    pdf.set_font("Deng", "B", 13)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(PW, 9, text, new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y()
    pdf.set_draw_color(44, 62, 80)
    pdf.line(LM, y, LM + PW, y)
    pdf.set_y(y + 3)
    pdf.set_text_color(0, 0, 0)

def step(num, title_text, description):
    pdf.set_font("Deng", "B", 10)
    pdf.cell(PW, 6, f"{num}. {title_text}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Deng", "", 9.5)
    pdf.set_text_color(60, 60, 60)
    old_l = pdf.l_margin
    pdf.set_left_margin(LM + 5)
    pdf.set_x(LM + 5)
    pdf.multi_cell(PW - 5, 5, description)
    pdf.set_left_margin(old_l)
    pdf.set_text_color(0, 0, 0)
    nl(2)

def separator():
    pdf.set_draw_color(200, 200, 200)
    y = pdf.get_y()
    pdf.line(LM, y, LM + PW, y)
    nl(3)

# ===== PAGE 1 =====
pdf.add_page()
title("Cornell Knowledge Base")
subtitle("Personal Study System \u2014 Rough Plan")
pdf.set_font("Deng", "", 10)
pdf.cell(PW, 6, "Jingyi Chen | Cornell MEng Systems Engineering | Aug 2026 \u2013 May 2027", new_x="LMARGIN", new_y="NEXT", align="C")
nl(5)

# Overview
pdf.set_font("Deng", "B", 11)
pdf.cell(PW, 7, "Overview", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Deng", "", 9.5)
pdf.multi_cell(PW, 5, "An AI-powered personal knowledge base for Cornell MEng coursework. Ingests lecture slides, audio transcripts, textbooks, homework, and exams into a Hindsight-powered memory system. Generates structured notes, enables natural language search across all material, and supports active recall through quizzing. Integrates with Obsidian for browsable notes and Hermes for conversational access.")
nl(4)

separator()

# Phase 1
phase_header("Phase 1: Core Infrastructure")

step(1, "Whisper Transcription Pipeline",
     "Install Whisper on RTX 4080 laptop. Test with sample lecture audio (YouTube lectures). "
     "Create a script: audio file \u2192 clean transcript with timestamps. "
     "Handle speaker diarization (professor vs student questions). "
     "Output: timestamped markdown transcript per lecture.")

step(2, "Document Extraction Pipeline",
     "PDF text extraction using pymupdf for slides, textbooks, homework, exams. "
     "Handle formulas (LaTeX extraction), diagrams (image extraction), tables. "
     "Output: structured markdown per document with metadata (course, type, chapter/lecture#).")

step(3, "Hindsight Integration",
     "Set up Hindsight retain/recall/reflect with course metadata schema. "
     "Metadata fields: course code, lecture number, source type (slide/transcript/textbook/homework/exam), topic, date. "
     "Test ingestion of sample material and verify retrieval quality. "
     "Validate graph traversal connects related concepts across lectures.")

separator()

# Phase 2
phase_header("Phase 2: Knowledge Processing")

step(4, "Lecture Note Generator",
     "Input: transcript (from Whisper) + slide PDF. "
     "Output: structured lecture notes with sections for key concepts, formulas, worked examples, "
     "action items, and connections to prior lectures. "
     "Retain structured facts into Hindsight with course/lecture metadata.")

step(5, "Textbook Processor",
     "Input: textbook chapter PDFs. "
     "Extract key concepts, definitions, theorems, proofs, examples. "
     "Retain into Hindsight with chapter/section metadata. "
     "Cross-reference with lecture notes for the same topic.")

step(6, "Homework/Exam Processor",
     "Input: homework assignments, past exams (PDF/images). "
     "Extract problem statements, solution approaches, common patterns, mistakes. "
     "Retain into Hindsight tagged by topic and difficulty. "
     "Build a pattern library for exam preparation.")

separator()

# Phase 3
phase_header("Phase 3: Hermes Skill")

step(7, "cornell-kb Skill",
     "Commands: /ingest (add new material), /review (generate course review), "
     "/quiz (active recall questions), /search (natural language query), "
     "/connect (show concept relationships across courses). "
     "Self-contained skill with Python scripts for processing and Hindsight API calls.")

step(8, "Teach Skill Integration",
     "Pull from Hindsight for context-aware quizzing. "
     "Track which topics have been reviewed and which are weak. "
     "Generate questions at different difficulty levels (recall, apply, analyze). "
     "Spaced repetition: surface weak topics more frequently before exams.")

separator()

# Phase 4
phase_header("Phase 4: Obsidian Layer")

step(9, "Vault Structure",
     "Create Cornell/ folder with per-course subfolders (e.g., Cornell/SE501/, Cornell/OR502/). "
     "Define lecture note templates with consistent structure. "
     "Auto-generate wikilinks between related concepts across courses. "
     "Maintain a master index per course with all lectures, topics, and connections.")

step(10, "Auto-Sync",
     "Hindsight recall results export as Obsidian notes on demand. "
     "Backlinks auto-generated when the same concept appears in multiple courses. "
     "Daily digest: new connections discovered by Hindsight graph traversal. "
     "Search results from Hermes queries saved as Obsidian notes for future reference.")

separator()

# Phase 5
phase_header("Phase 5: Exam and Review")

step(11, "Comprehensive Review Generator",
     "Per-course review generated from all stored material (lectures, textbook, homework). "
     "Output: concept map, formula sheet, key problem patterns, weak area summary. "
     "Cross-course connections highlighted (e.g., optimization theory in SE501 connects to OR502).")

step(12, "Spaced Repetition System",
     "Track what has been reviewed and quiz performance. "
     "Surface weak topics more frequently as exams approach. "
     "Generate targeted practice problems from homework/exam pattern library. "
     "Pre-exam summary: top 10 topics to review based on weakness analysis.")

nl(5)
separator()

# Footer
pdf.set_font("Deng", "", 9)
pdf.set_text_color(100, 100, 100)
pdf.cell(PW, 5, "Status: DRAFT \u2014 Revising before detailed planning", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.cell(PW, 5, "Created: 2026-07-09 | Last updated: 2026-07-09", new_x="LMARGIN", new_y="NEXT", align="C")

out = r"C:\Users\TobyC\hermes_related\Cornell_KB\rough_plan.pdf"
pdf.output(out)
print(f"PDF saved: {out}")
