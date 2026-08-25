"""Transcript quality verification with deterministic checks and Luna/Codex review.

This module deliberately separates three things:

* deterministic inspection of the timestamped transcript;
* a structured semantic review through Hermes' ``openai-codex`` route;
* conservative application of only high-confidence, exact-match corrections.

The raw transcript is never modified.  A successful review produces a verified
sidecar and a JSON report containing the evidence used to create it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

TIMESTAMP_RE = re.compile(
    r"^\s*\[(?P<start>\d+(?:\.\d+)?)s\s*->\s*"
    r"(?P<end>\d+(?:\.\d+)?)s\]\s*(?P<text>.*?)\s*$"
)

REVIEW_SCHEMA_VERSION = 1
LUNA_MODEL = "gpt-5.6-luna"
LUNA_PROVIDER = "openai-codex"
DEFAULT_MAX_CHUNK_CHARS = 12_000
DEFAULT_GAP_THRESHOLD_SECONDS = 30.0
DEFAULT_CORRECTION_CONFIDENCE = 0.90


@dataclass(frozen=True)
class TranscriptSegment:
    """One timestamped transcript segment."""

    index: int
    start: float
    end: float
    text: str
    raw_line: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "text": self.text,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_text(text: str) -> str:
    """Normalize text for duplicate detection, not for transcript replacement."""
    return re.sub(r"\s+", " ", text.casefold()).strip()


def parse_transcript(text: str) -> list[TranscriptSegment]:
    """Parse timestamped lines and ignore non-segment headers/blank lines."""
    segments: list[TranscriptSegment] = []
    for raw_line in text.splitlines():
        match = TIMESTAMP_RE.match(raw_line)
        if not match:
            continue
        segments.append(
            TranscriptSegment(
                index=len(segments),
                start=float(match.group("start")),
                end=float(match.group("end")),
                text=match.group("text").strip(),
                raw_line=raw_line,
            )
        )
    return segments


def inspect_transcript(
    text: str,
    *,
    gap_threshold_seconds: float = DEFAULT_GAP_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """Run deterministic checks without contacting an LLM or audio service."""
    if gap_threshold_seconds <= 0:
        raise ValueError("gap_threshold_seconds must be positive")

    segments = parse_transcript(text)
    errors: list[str] = []
    warnings: list[str] = []
    large_gaps: list[dict[str, Any]] = []
    overlaps: list[dict[str, Any]] = []

    if not segments:
        errors.append("No timestamped transcript segments were found")

    previous: TranscriptSegment | None = None
    for segment in segments:
        if segment.end < segment.start:
            errors.append(f"Segment {segment.index} ends before it starts")
        if not segment.text:
            errors.append(f"Segment {segment.index} has empty text")
        if previous is not None:
            if segment.start < previous.start:
                errors.append(
                    f"Segment {segment.index} starts before segment {previous.index}"
                )
            if segment.start < previous.end:
                overlaps.append(
                    {
                        "previous_index": previous.index,
                        "index": segment.index,
                        "overlap_seconds": round(previous.end - segment.start, 3),
                    }
                )
            gap = segment.start - previous.end
            if gap > gap_threshold_seconds:
                large_gaps.append(
                    {
                        "previous_index": previous.index,
                        "index": segment.index,
                        "gap_seconds": round(gap, 3),
                    }
                )
        previous = segment

    normalized_counts: dict[str, int] = {}
    for segment in segments:
        normalized = _normalize_text(segment.text)
        if normalized:
            normalized_counts[normalized] = normalized_counts.get(normalized, 0) + 1
    repeated_text_count = sum(max(count - 1, 0) for count in normalized_counts.values())

    if large_gaps:
        warnings.append(f"Found {len(large_gaps)} gap(s) longer than the threshold")
    if overlaps:
        warnings.append(f"Found {len(overlaps)} timestamp overlap(s)")
    if repeated_text_count:
        warnings.append(f"Found {repeated_text_count} repeated segment text value(s)")

    technical_checks = {
        "segment_count": len(segments),
        "timestamp_order": "fail" if any("starts before" in e for e in errors) else "pass",
        "timestamp_ranges": "fail" if any("ends before" in e for e in errors) else "pass",
        "nonempty_text": "fail" if any("empty text" in e for e in errors) else "pass",
        "large_gaps": large_gaps,
        "overlaps": overlaps,
        "repeated_text_count": repeated_text_count,
        "last_end_seconds": segments[-1].end if segments else None,
    }

    status = "failed" if errors else ("needs_review" if warnings else "pass")
    return {
        "status": status,
        "segment_count": len(segments),
        "technical_checks": technical_checks,
        "warnings": warnings,
        "errors": errors,
    }


def chunk_transcript(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    overlap_segments: int = 1,
) -> list[dict[str, Any]]:
    """Split a timestamped transcript into bounded review chunks.

    Chunks overlap by one segment by default so a sentence crossing a boundary
    is not reviewed without its immediate context.  The caller deduplicates
    findings after the model returns.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    if overlap_segments < 0:
        raise ValueError("overlap_segments cannot be negative")

    segments = parse_transcript(text)
    if not segments:
        return []

    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    current_chars = 0
    for segment in segments:
        line_len = len(segment.raw_line) + 1
        if current and current_chars + line_len > max_chars:
            chunks.append(current)
            overlap = min(overlap_segments, len(current))
            current = current[-overlap:] if overlap else []
            current_chars = sum(len(item.raw_line) + 1 for item in current)
        current.append(segment)
        current_chars += line_len
    if current:
        chunks.append(current)

    return [
        {
            "chunk_index": index,
            "start_seconds": chunk[0].start,
            "end_seconds": chunk[-1].end,
            "text": "\n".join(segment.raw_line for segment in chunk),
            "segment_indices": [segment.index for segment in chunk],
        }
        for index, chunk in enumerate(chunks)
    ]


def build_luna_prompt(
    chunk: dict[str, Any],
    *,
    course: str | None = None,
    lecture: int | None = None,
    topic: str | None = None,
    total_chunks: int = 1,
) -> str:
    """Build a compact, JSON-only prompt for one Luna transcript review."""
    context = []
    if course:
        context.append(f"Course: {course}")
    if lecture is not None:
        context.append(f"Lecture: {lecture}")
    if topic:
        context.append(f"Topic: {topic}")
    context_text = "\n".join(context) if context else "(course metadata unavailable)"
    return f"""You are the semantic transcript verifier for a university lecture.

{context_text}
Review chunk {chunk['chunk_index'] + 1} of {total_chunks}, covering approximately
{chunk['start_seconds']:.2f}s to {chunk['end_seconds']:.2f}s.

Your job is to identify likely transcription problems, not to rewrite the lecture.
Use your subject knowledge to flag technical terms, formulas, names, units,
contradictions, obvious hallucinations, and sentences that do not make sense.
Do not flag ordinary conversational imperfections. Do not invent a correction
when the evidence is weak. A transcript-only review cannot prove what the audio
said, so label uncertain audio-level judgments as uncertain.

Return ONLY valid JSON with this schema:
{{
  "status": "pass" | "needs_review",
  "findings": [
    {{
      "segment_start": 0.0,
      "segment_end": 0.0,
      "severity": "minor" | "major" | "blocker",
      "category": "term" | "formula" | "number" | "coherence" | "hallucination" | "other",
      "original_text": "exact transcript text when available",
      "replacement_text": "only a high-confidence correction; otherwise empty",
      "reason": "specific technical reason",
      "confidence": 0.0
    }}
  ]
}}
Use an empty findings list and status pass when no issue is supported.

Transcript chunk:
{chunk['text']}
"""


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
    return cleaned.strip()


def parse_luna_review(text: str) -> dict[str, Any]:
    """Parse and validate Luna's machine-readable review response."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Luna returned an empty review")
    cleaned = _strip_json_fence(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        # Permit a short prose preamble while still requiring a JSON object.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Luna review was not valid JSON")
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as error:
            raise ValueError(f"Luna review was not valid JSON: {error}") from error

    if not isinstance(payload, dict):
        raise ValueError("Luna review must be a JSON object")
    status = str(payload.get("status", "needs_review")).strip().lower()
    if status in {"review", "check", "warning"}:
        status = "needs_review"
    if status not in {"pass", "needs_review", "failed"}:
        raise ValueError(f"Unsupported Luna review status: {status!r}")

    raw_findings = payload.get("findings", [])
    if not isinstance(raw_findings, list):
        raise ValueError("Luna review findings must be a list")

    findings: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_findings):
        if not isinstance(raw, dict):
            raise ValueError(f"Luna finding {index} must be an object")
        try:
            start = float(raw["segment_start"])
            end = float(raw["segment_end"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Luna finding {index} has invalid segment bounds") from error
        if start < 0 or end < start:
            raise ValueError(f"Luna finding {index} has invalid segment bounds")
        try:
            confidence = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Luna finding {index} has invalid confidence") from error
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Luna finding {index} confidence must be between 0 and 1")
        findings.append(
            {
                "segment_start": start,
                "segment_end": end,
                "severity": str(raw.get("severity", "minor")),
                "category": str(raw.get("category", "other")),
                "original_text": str(raw.get("original_text", "")).strip(),
                "replacement_text": str(raw.get("replacement_text", "")).strip(),
                "reason": str(raw.get("reason", "")).strip(),
                "confidence": confidence,
            }
        )

    if findings and status == "pass":
        status = "needs_review"
    return {"status": status, "findings": findings}


def merge_luna_reviews(reviews: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Deduplicate chunk findings and produce one canonical review payload."""
    findings: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    statuses: list[str] = []
    for chunk_index, review in enumerate(reviews):
        status = review.get("status", "needs_review")
        statuses.append(status)
        for finding in review.get("findings", []):
            key = (
                round(float(finding["segment_start"]), 2),
                round(float(finding["segment_end"]), 2),
                finding.get("original_text", ""),
                finding.get("replacement_text", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            copied = dict(finding)
            copied["chunk_index"] = chunk_index
            findings.append(copied)

    if "failed" in statuses:
        status = "failed"
    elif findings or "needs_review" in statuses:
        status = "needs_review"
    else:
        status = "pass"
    return {"status": status, "findings": findings, "chunks_reviewed": len(statuses)}


def apply_verified_corrections(
    transcript_text: str,
    review: dict[str, Any],
    *,
    min_confidence: float = DEFAULT_CORRECTION_CONFIDENCE,
) -> str:
    """Apply only exact-match, high-confidence segment replacements.

    A finding is ignored unless its timestamp range and original text identify
    exactly one segment.  This makes the sidecar conservative by construction;
    uncertain findings remain in the JSON report for human review.
    """
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")

    replacements: dict[int, str] = {}
    segments = parse_transcript(transcript_text)
    for finding in review.get("findings", []):
        try:
            confidence = float(finding.get("confidence", 0.0))
            start = float(finding["segment_start"])
            end = float(finding["segment_end"])
        except (KeyError, TypeError, ValueError):
            continue
        original = str(finding.get("original_text", "")).strip()
        replacement = str(finding.get("replacement_text", "")).strip()
        if confidence < min_confidence or not original or not replacement:
            continue
        for segment in segments:
            if abs(segment.start - start) > 0.02 or abs(segment.end - end) > 0.02:
                continue
            if segment.text.strip() != original:
                continue
            replacements[segment.index] = replacement
            break

    if not replacements:
        return transcript_text

    output_lines: list[str] = []
    segment_index = 0
    for raw_line in transcript_text.splitlines():
        match = TIMESTAMP_RE.match(raw_line)
        if not match:
            output_lines.append(raw_line)
            continue
        replacement = replacements.get(segment_index)
        if replacement is None:
            output_lines.append(raw_line)
        else:
            output_lines.append(
                f"[{float(match.group('start')):.2f}s -> "
                f"{float(match.group('end')):.2f}s] {replacement}"
            )
        segment_index += 1
    suffix = "\n" if transcript_text.endswith("\n") else ""
    return "\n".join(output_lines) + suffix


class HermesLunaRunner:
    """Run one review through Hermes' OAuth-backed Codex model route."""

    provider = LUNA_PROVIDER
    model = LUNA_MODEL

    def __init__(
        self,
        *,
        executable: str | None = None,
        model: str = LUNA_MODEL,
        provider: str = LUNA_PROVIDER,
        timeout: float = 900,
        usage_dir: str | Path | None = None,
        cwd: str | Path | None = None,
        run_command: Callable[..., Any] = subprocess.run,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.executable = executable or shutil.which("hermes") or "hermes"
        self.model = model
        self.provider = provider
        self.timeout = timeout
        self.usage_dir = Path(usage_dir) if usage_dir else None
        self.cwd = str(cwd) if cwd else None
        self._run_command = run_command
        self._counter = 0

    def review(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("Cannot review an empty prompt")
        command = [
            self.executable,
            "-z",
            prompt,
            "-m",
            self.model,
            "--provider",
            self.provider,
        ]
        if self.usage_dir is not None:
            self.usage_dir.mkdir(parents=True, exist_ok=True)
            self._counter += 1
            usage_path = self.usage_dir / f"luna-review-{self._counter:03d}.json"
            command.extend(["--usage-file", str(usage_path)])

        result = self._run_command(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=self.cwd,
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "no error output").strip()
            raise RuntimeError(f"Luna/Codex review failed with exit code {result.returncode}: {detail[:500]}")
        response = (result.stdout or "").strip()
        if not response:
            raise RuntimeError("Luna/Codex review returned no output")
        return response


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def verify_transcript(
    transcript_path: str | Path,
    *,
    output_dir: str | Path,
    course: str | None = None,
    lecture: int | None = None,
    topic: str | None = None,
    runner: Any | None = None,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    overlap_segments: int = 1,
    gap_threshold_seconds: float = DEFAULT_GAP_THRESHOLD_SECONDS,
    correction_confidence: float = DEFAULT_CORRECTION_CONFIDENCE,
) -> dict[str, Any]:
    """Inspect and semantically review a transcript, writing durable artifacts."""
    source = Path(transcript_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Transcript not found: {source}")
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw_text = source.read_text(encoding="utf-8")
    local_report = inspect_transcript(
        raw_text,
        gap_threshold_seconds=gap_threshold_seconds,
    )
    chunks = chunk_transcript(
        raw_text,
        max_chars=max_chunk_chars,
        overlap_segments=overlap_segments,
    )

    review_runner = runner
    if review_runner is None:
        review_runner = HermesLunaRunner(usage_dir=output / "luna-usage")

    review_payloads: list[dict[str, Any]] = []
    review_errors: list[str] = []
    if local_report["errors"]:
        review_errors.append("Deterministic transcript checks failed; semantic review was skipped")
    else:
        for chunk in chunks:
            prompt = build_luna_prompt(
                chunk,
                course=course,
                lecture=lecture,
                topic=topic,
                total_chunks=len(chunks),
            )
            try:
                review_payloads.append(parse_luna_review(review_runner.review(prompt)))
            except Exception as error:
                review_errors.append(
                    f"Chunk {chunk['chunk_index'] + 1}/{len(chunks)} review failed: {error}"
                )
                break

    merged_review = merge_luna_reviews(review_payloads)
    if review_errors:
        overall_status = "failed"
    elif local_report["status"] == "failed" or merged_review["status"] == "failed":
        overall_status = "failed"
    elif local_report["status"] == "needs_review" or merged_review["status"] == "needs_review":
        overall_status = "needs_review"
    else:
        overall_status = "pass"

    stem = source.stem
    report_path = output / f"{stem}.transcript-review.json"
    verified_path = output / f"{stem}.verified.txt"
    report: dict[str, Any] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "status": overall_status,
        "source_transcript": str(source),
        "source_sha256": _sha256_file(source),
        "course": course,
        "lecture": lecture,
        "topic": topic,
        "local_checks": local_report,
        "review": {
            "provider": getattr(review_runner, "provider", LUNA_PROVIDER),
            "model": getattr(review_runner, "model", LUNA_MODEL),
            "status": merged_review["status"] if review_payloads else "failed",
            "chunks_reviewed": merged_review["chunks_reviewed"],
            "chunk_size_chars": max_chunk_chars,
            "findings": merged_review["findings"],
            "errors": review_errors,
        },
        "corrections": {
            "policy": "exact timestamp + exact original text + confidence threshold",
            "minimum_confidence": correction_confidence,
            "applied_count": 0,
        },
        "report_path": str(report_path),
        "review_path": str(report_path),
    }

    if overall_status != "failed":
        verified_text = apply_verified_corrections(
            raw_text,
            merged_review,
            min_confidence=correction_confidence,
        )
        verified_path.write_text(verified_text, encoding="utf-8")
        raw_segments = parse_transcript(raw_text)
        verified_segments = parse_transcript(verified_text)
        applied_count = sum(
            1
            for raw_segment, verified_segment in zip(raw_segments, verified_segments)
            if raw_segment.text != verified_segment.text
        )
        report["corrections"]["applied_count"] = applied_count
        report["verified_transcript_path"] = str(verified_path)

    _write_json(report_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a timestamped lecture transcript")
    parser.add_argument("transcript", help="Raw timestamped transcript file")
    parser.add_argument("--output-dir", required=True, help="Directory for review artifacts")
    parser.add_argument("--course", default=None)
    parser.add_argument("--lecture", type=int, default=None)
    parser.add_argument("--topic", default=None)
    parser.add_argument("--max-chunk-chars", type=int, default=DEFAULT_MAX_CHUNK_CHARS)
    parser.add_argument("--overlap-segments", type=int, default=1)
    parser.add_argument("--gap-threshold", type=float, default=DEFAULT_GAP_THRESHOLD_SECONDS)
    parser.add_argument("--correction-confidence", type=float, default=DEFAULT_CORRECTION_CONFIDENCE)
    parser.add_argument("--luna-executable", default=None)
    parser.add_argument("--luna-model", default=LUNA_MODEL)
    parser.add_argument("--luna-provider", default=LUNA_PROVIDER)
    parser.add_argument("--luna-timeout", type=float, default=900)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.max_chunk_chars < 1 or args.overlap_segments < 0 or args.gap_threshold <= 0:
        raise SystemExit("Invalid chunk, overlap, or gap threshold")
    if not 0 <= args.correction_confidence <= 1:
        raise SystemExit("--correction-confidence must be between 0 and 1")
    runner = HermesLunaRunner(
        executable=args.luna_executable,
        model=args.luna_model,
        provider=args.luna_provider,
        timeout=args.luna_timeout,
        usage_dir=Path(args.output_dir) / "luna-usage",
        cwd=Path(__file__).resolve().parents[2],
    )
    report = verify_transcript(
        args.transcript,
        output_dir=args.output_dir,
        course=args.course,
        lecture=args.lecture,
        topic=args.topic,
        runner=runner,
        max_chunk_chars=args.max_chunk_chars,
        overlap_segments=args.overlap_segments,
        gap_threshold_seconds=args.gap_threshold,
        correction_confidence=args.correction_confidence,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] == "failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
