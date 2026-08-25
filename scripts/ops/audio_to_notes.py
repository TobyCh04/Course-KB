"""End-to-end transcript verification plus DeepSeek lecture-note generation.

The orchestration boundary is intentional:

* transcription remains a local media step (usually on the RTX laptop);
* Luna/Codex verifies the resulting transcript and writes a report/sidecar;
* DeepSeek generates the notes from the verified sidecar;
* raw input is preserved and never overwritten.

No OpenViking or Hindsight write is performed by this command.  Indexing and
memory retention remain explicit downstream operations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.media.transcript_verifier import (
    HermesLunaRunner,
    verify_transcript,
)
from scripts.notes import note_generator


def _load_json(path: str | Path | None, *, default: Any) -> Any:
    if path is None:
        return default
    source = Path(path).expanduser()
    return json.loads(source.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def run_audio_to_notes(
    *,
    transcript_path: str | Path,
    output_dir: str | Path,
    course: str,
    lecture: int,
    topic: str = "Lecture Content",
    facts_path: str | Path | None = None,
    diagrams_path: str | Path | None = None,
    note_output: str | Path | None = None,
    note_model: str = note_generator.DEFAULT_MODEL,
    note_api_key: str | None = None,
    note_api_url: str | None = None,
    luna_runner: Any | None = None,
    note_llm_call: Callable[..., str] | None = None,
    run_note_fact_check: bool = True,
    fact_check_workers: int = 2,
    source_mode: str = "external",
    max_transcript_chunk_chars: int = 12_000,
    correction_confidence: float = 0.90,
    web_verify: bool = False,
) -> dict[str, Any]:
    """Verify a transcript with Luna, then generate notes with DeepSeek.

    Note generation is refused unless the Luna stage produces a verified
    transcript sidecar.  Callers that intentionally want an unverified draft
    must use ``note_generator`` directly and accept that it is outside this
    end-to-end contract.
    """
    raw_path = Path(transcript_path).expanduser().resolve()
    if not raw_path.is_file():
        raise FileNotFoundError(f"Transcript not found: {raw_path}")
    if note_model not in note_generator.ALLOWED_MODELS:
        allowed = ", ".join(sorted(note_generator.ALLOWED_MODELS))
        raise ValueError(f"Unsupported note model {note_model!r}; allowed: {allowed}")
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    if luna_runner is None:
        luna_runner = HermesLunaRunner(
            usage_dir=output / "luna-usage",
            cwd=Path(__file__).resolve().parents[2],
        )

    verification = verify_transcript(
        raw_path,
        output_dir=output,
        course=course,
        lecture=lecture,
        topic=topic,
        runner=luna_runner,
        max_chunk_chars=max_transcript_chunk_chars,
        correction_confidence=correction_confidence,
    )
    verified_path_value = verification.get("verified_transcript_path")
    if verification.get("status") == "failed" or not verified_path_value:
        errors = verification.get("review", {}).get("errors", [])
        detail = "; ".join(errors) if errors else "no verified transcript sidecar was produced"
        raise RuntimeError(f"Cannot generate notes: transcript verification failed ({detail})")

    verified_path = Path(verified_path_value)
    verified_text = verified_path.read_text(encoding="utf-8")
    facts = _load_json(facts_path, default=None)
    diagrams = _load_json(diagrams_path, default=None)
    if facts is not None and not isinstance(facts, list):
        raise ValueError("facts JSON must contain a list")
    if diagrams is not None and not isinstance(diagrams, list):
        raise ValueError("diagrams JSON must contain a list")

    if note_output:
        note_path = Path(note_output).expanduser().resolve()
    else:
        note_path = output / f"{raw_path.stem}.notes.md"
        try:
            output.relative_to(note_generator.DEFAULT_COURSE_ROOT)
        except ValueError:
            pass
        else:
            note_path = Path(
                note_generator.default_note_output_path(course, lecture)
            ).expanduser().resolve()
    source_path = output / f"{raw_path.stem}.sources.md"
    source_reference = source_path.name

    note_text = note_generator.generate_notes(
        transcript_text=verified_text,
        facts=facts,
        diagrams=diagrams,
        course_code=course,
        lecture=lecture,
        topic=topic,
        backend="deepseek",
        model=note_model,
        api_key=note_api_key,
        api_url=note_api_url,
        run_fact_check=run_note_fact_check,
        fact_check_workers=fact_check_workers,
        web_verify=web_verify,
        source_mode=source_mode,
        source_reference=source_reference,
        llm_call=note_llm_call or note_generator.call_llm,
    )
    note_generator.save_note(note_text, note_path)

    if source_mode == "external":
        source_text = note_generator.build_source_verification(
            verified_text,
            facts,
            diagrams,
        )
        note_generator.save_note(source_text, source_path)

    manifest_path = output / f"{raw_path.stem}.audio-to-notes.json"
    manifest = {
        "schema_version": 1,
        "pipeline": "audio_to_notes",
        "status": "complete",
        "raw_transcript_path": str(raw_path),
        "verified_transcript_path": str(verified_path),
        "review_path": verification["review_path"],
        "note_path": str(note_path),
        "note_model": note_model,
        "source_path": str(source_path) if source_mode == "external" else None,
        "course": course,
        "lecture": lecture,
        "topic": topic,
        "transcript_verification": {
            "provider": verification["review"]["provider"],
            "model": verification["review"]["model"],
            "status": verification["status"],
            "findings": len(verification["review"]["findings"]),
            "corrections_applied": verification["corrections"]["applied_count"],
        },
        "verification": {
            "status": verification["status"],
            "provider": verification["review"]["provider"],
            "model": verification["review"]["model"],
            "review_path": verification["review_path"],
            "verified_transcript_path": verification["verified_transcript_path"],
        },
        "note_generation": {
            "provider": "deepseek",
            "model": note_model,
            "fact_check_enabled": run_note_fact_check,
            "web_verify_enabled": web_verify,
        },
        "raw_preserved": True,
    }
    manifest["manifest_path"] = str(manifest_path)
    _write_json(manifest_path, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a transcript with Luna/Codex, then generate DeepSeek lecture notes"
    )
    parser.add_argument("--transcript", required=True, help="Raw timestamped transcript file")
    parser.add_argument("--output-dir", required=True, help="Directory for all generated artifacts")
    parser.add_argument("--course", required=True, help="Course code")
    parser.add_argument("--lecture", required=True, type=int, help="Lecture number")
    parser.add_argument("--topic", default="Lecture Content")
    parser.add_argument("--facts", default=None, help="Optional chunked facts JSON")
    parser.add_argument("--diagrams", default=None, help="Optional diagram descriptions JSON")
    parser.add_argument("--note-output", default=None, help="Optional final Markdown path")
    parser.add_argument(
        "--note-model",
        choices=sorted(note_generator.ALLOWED_MODELS),
        default=note_generator.DEFAULT_MODEL,
        help="DeepSeek model for note generation (Pro is the default)",
    )
    parser.add_argument("--api-key", default=None, help="DeepSeek API key override")
    parser.add_argument("--api-url", default=None, help="DeepSeek chat-completions endpoint override")
    parser.add_argument("--no-note-fact-check", action="store_true")
    parser.add_argument("--fact-check-workers", type=int, default=2)
    parser.add_argument("--web-verify", action="store_true")
    parser.add_argument("--source-mode", choices=("external", "inline", "none"), default="external")
    parser.add_argument("--max-transcript-chunk-chars", type=int, default=12_000)
    parser.add_argument("--correction-confidence", type=float, default=0.90)
    parser.add_argument("--luna-executable", default=None)
    parser.add_argument("--luna-model", default="gpt-5.6-luna")
    parser.add_argument("--luna-provider", default="openai-codex")
    parser.add_argument("--luna-timeout", type=float, default=900)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.fact_check_workers < 1 or args.max_transcript_chunk_chars < 1:
        raise SystemExit("workers and transcript chunk size must be at least 1")
    if not 0 <= args.correction_confidence <= 1:
        raise SystemExit("--correction-confidence must be between 0 and 1")
    output_dir = Path(args.output_dir).expanduser()
    runner = HermesLunaRunner(
        executable=args.luna_executable,
        model=args.luna_model,
        provider=args.luna_provider,
        timeout=args.luna_timeout,
        usage_dir=output_dir / "luna-usage",
        cwd=Path(__file__).resolve().parents[2],
    )
    manifest = run_audio_to_notes(
        transcript_path=args.transcript,
        output_dir=output_dir,
        course=args.course,
        lecture=args.lecture,
        topic=args.topic,
        facts_path=args.facts,
        diagrams_path=args.diagrams,
        note_output=args.note_output,
        note_model=args.note_model,
        note_api_key=args.api_key,
        note_api_url=args.api_url,
        luna_runner=runner,
        run_note_fact_check=not args.no_note_fact_check,
        fact_check_workers=args.fact_check_workers,
        source_mode=args.source_mode,
        max_transcript_chunk_chars=args.max_transcript_chunk_chars,
        correction_confidence=args.correction_confidence,
        web_verify=args.web_verify,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
