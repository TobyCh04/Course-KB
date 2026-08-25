"""Offline contract tests for the audio-to-notes model split."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.audio_to_notes import run_audio_to_notes


TRANSCRIPT = """[0.00s -> 2.00s] Feedback compares a measured output to a reference.
[2.00s -> 4.00s] The error signal drives the controller.
"""


class FakeLuna:
    def review(self, _prompt: str) -> str:
        return json.dumps({"status": "pass", "findings": []})


def test_audio_to_notes_uses_verified_transcript_and_keeps_raw_artifact(tmp_path):
    raw_path = tmp_path / "Lecture01.txt"
    raw_path.write_text(TRANSCRIPT, encoding="utf-8")

    def fake_note_llm(prompt, **kwargs):
        assert "Feedback compares" in prompt
        assert kwargs["model"] == "deepseek-v4-pro"
        return "# Lecture 1\n\n## Key Concepts\n- Feedback compares output to a reference."

    result = run_audio_to_notes(
        transcript_path=raw_path,
        output_dir=tmp_path / "artifacts",
        course="TEST-SE424",
        lecture=1,
        topic="Feedback",
        luna_runner=FakeLuna(),
        note_llm_call=fake_note_llm,
        run_note_fact_check=False,
    )

    assert result["verification"]["status"] == "pass"
    assert Path(result["raw_transcript_path"]).read_text(encoding="utf-8") == TRANSCRIPT
    assert Path(result["verified_transcript_path"]).is_file()
    assert Path(result["review_path"]).is_file()
    assert Path(result["note_path"]).is_file()
    assert result["note_model"] == "deepseek-v4-pro"


def test_audio_to_notes_refuses_note_generation_when_luna_review_is_missing(tmp_path):
    raw_path = tmp_path / "Lecture01.txt"
    raw_path.write_text(TRANSCRIPT, encoding="utf-8")

    class NoReview:
        def review(self, _prompt: str) -> str:
            raise RuntimeError("Codex unavailable")

    with pytest.raises(RuntimeError, match="transcript verification"):
        run_audio_to_notes(
            transcript_path=raw_path,
            output_dir=tmp_path / "artifacts",
            course="TEST-SE424",
            lecture=1,
            topic="Feedback",
            luna_runner=NoReview(),
            note_llm_call=lambda *_args, **_kwargs: "should not run",
            run_note_fact_check=False,
        )


def test_audio_to_notes_can_select_flash_for_an_explicit_draft_pass(tmp_path):
    raw_path = tmp_path / "Lecture01.txt"
    raw_path.write_text(TRANSCRIPT, encoding="utf-8")
    seen = {}

    def fake_note_llm(_prompt, **kwargs):
        seen["model"] = kwargs["model"]
        return "# Draft notes"

    result = run_audio_to_notes(
        transcript_path=raw_path,
        output_dir=tmp_path / "artifacts",
        course="TEST-SE424",
        lecture=1,
        topic="Feedback",
        note_model="deepseek-v4-flash",
        luna_runner=FakeLuna(),
        note_llm_call=fake_note_llm,
        run_note_fact_check=False,
    )

    assert seen["model"] == "deepseek-v4-flash"
    assert result["note_model"] == "deepseek-v4-flash"
