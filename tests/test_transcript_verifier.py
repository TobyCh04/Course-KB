"""Offline contract tests for the transcript verification stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.media.transcript_verifier import (
    HermesLunaRunner,
    apply_verified_corrections,
    inspect_transcript,
    parse_luna_review,
    parse_transcript,
    verify_transcript,
)


RAW_TRANSCRIPT = """Language: en (99%)
Duration: 12.0s
Engine: Whisper large-v3-turbo
==================================================

[0.00s -> 2.00s] The reference signal is compared with the measured output.
[2.20s -> 4.00s] The error drives the controller.
[10.00s -> 12.00s] The reference signal is compared with the measured output.
"""


class FakeLuna:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []

    def review(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_parse_transcript_preserves_timestamped_segments_and_ignores_headers():
    segments = parse_transcript(RAW_TRANSCRIPT)

    assert len(segments) == 3
    assert segments[0].start == 0.0
    assert segments[1].end == 4.0
    assert segments[2].text.startswith("The reference signal")


def test_inspect_transcript_reports_gaps_and_repeated_text_without_failing_parse():
    report = inspect_transcript(RAW_TRANSCRIPT, gap_threshold_seconds=5.0)

    assert report["status"] == "needs_review"
    assert report["segment_count"] == 3
    assert report["technical_checks"]["timestamp_order"] == "pass"
    assert report["technical_checks"]["large_gaps"][0]["gap_seconds"] == pytest.approx(6.0)
    assert report["technical_checks"]["repeated_text_count"] == 1


def test_parse_luna_review_requires_structured_findings_and_normalizes_defaults():
    review = parse_luna_review(
        """```json
        {
          "status": "needs_review",
          "findings": [{
            "segment_start": 2.2,
            "segment_end": 4.0,
            "severity": "minor",
            "category": "term",
            "original_text": "The error drives the controller.",
            "replacement_text": "The error signal drives the controller.",
            "reason": "The technical phrase is incomplete.",
            "confidence": 0.94
          }]
        }
        ```"""
    )

    assert review["status"] == "needs_review"
    assert review["findings"][0]["confidence"] == pytest.approx(0.94)
    assert review["findings"][0]["replacement_text"].startswith("The error signal")


def test_apply_verified_corrections_only_applies_exact_high_confidence_matches():
    review = {
        "findings": [
            {
                "segment_start": 2.2,
                "segment_end": 4.0,
                "original_text": "The error drives the controller.",
                "replacement_text": "The error signal drives the controller.",
                "confidence": 0.94,
            },
            {
                "segment_start": 0.0,
                "segment_end": 2.0,
                "original_text": "wrong text",
                "replacement_text": "unsafe replacement",
                "confidence": 0.99,
            },
        ]
    }

    corrected = apply_verified_corrections(RAW_TRANSCRIPT, review)

    assert "The error signal drives the controller." in corrected
    assert "unsafe replacement" not in corrected
    assert "The reference signal is compared with the measured output." in corrected


def test_verify_transcript_writes_report_and_verified_sidecar(tmp_path):
    transcript_path = tmp_path / "lecture.txt"
    transcript_path.write_text(RAW_TRANSCRIPT, encoding="utf-8")
    runner = FakeLuna(
        json.dumps(
            {
                "status": "needs_review",
                "findings": [
                    {
                        "segment_start": 2.2,
                        "segment_end": 4.0,
                        "severity": "minor",
                        "category": "term",
                        "original_text": "The error drives the controller.",
                        "replacement_text": "The error signal drives the controller.",
                        "reason": "Clarifies the technical term.",
                        "confidence": 0.94,
                    }
                ],
            }
        )
    )

    result = verify_transcript(
        transcript_path,
        output_dir=tmp_path / "verification",
        course="TEST-SE424",
        lecture=1,
        runner=runner,
        max_chunk_chars=10000,
    )

    assert result["status"] == "needs_review"
    assert result["review"]["provider"] == "openai-codex"
    assert Path(result["review_path"]).is_file()
    assert Path(result["verified_transcript_path"]).is_file()
    assert "error signal" in Path(result["verified_transcript_path"]).read_text(encoding="utf-8")
    assert result["corrections"]["applied_count"] == 1
    persisted = json.loads(Path(result["review_path"]).read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1
    assert len(runner.prompts) == 1


def test_hermes_luna_runner_uses_codex_provider_and_model_without_shell(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))

        class Completed:
            returncode = 0
            stdout = '{"status":"pass","findings":[]}'
            stderr = ""

        return Completed()

    runner = HermesLunaRunner(
        executable="hermes",
        model="gpt-5.6-luna",
        provider="openai-codex",
        run_command=fake_run,
        usage_dir=tmp_path,
    )

    response = runner.review("review this transcript chunk")

    assert '"status":"pass"' in response
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:2] == ["hermes", "-z"]
    assert command[2] == "review this transcript chunk"
    assert ["-m", "gpt-5.6-luna"] == command[3:5]
    assert ["--provider", "openai-codex"] == command[5:7]
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert any(str(arg).endswith(".json") for arg in command)
