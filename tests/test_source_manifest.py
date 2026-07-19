import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.source_manifest import (  # noqa: E402
    build_lexical_index_from_manifest,
    dry_run_manifest,
    validate_manifest,
)


def _manifest_for(path: Path, **metadata):
    return {
        "schema_version": 1,
        "hash_algorithm": "sha256",
        "required_fields": ["source_path", "source_hash", "source_type"],
        "optional_fields": ["course", "semester", "date", "lecture", "corpus"],
        "sources": [
            {
                "source_path": str(path),
                "source_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source_type": "homework",
                **metadata,
            }
        ],
    }


def test_manifest_allows_external_test_source_without_lecture(tmp_path):
    pdf = tmp_path / "exam.pdf"
    pdf.write_bytes(b"test pdf bytes")
    manifest = _manifest_for(pdf, course="TEST", semester="TEST", corpus="test")

    assert validate_manifest(manifest, tmp_path) == []


def test_manifest_rejects_hash_mismatch(tmp_path):
    pdf = tmp_path / "exam.pdf"
    pdf.write_bytes(b"test pdf bytes")
    manifest = _manifest_for(pdf, course="TEST", corpus="test")
    manifest["sources"][0]["source_hash"] = "0" * 64

    errors = validate_manifest(manifest, tmp_path)

    assert any("hash mismatch" in error for error in errors)


def test_manifest_dry_run_returns_optional_lecture_metadata(tmp_path):
    pdf = tmp_path / "homework.pdf"
    pdf.write_bytes(b"test pdf bytes")
    manifest = _manifest_for(pdf, course="TEST", semester="TEST", corpus="test")

    resources = dry_run_manifest(manifest, tmp_path)

    assert len(resources) == 1
    assert resources[0].lecture is None
    assert resources[0].metadata["course"] == "TEST"
    assert resources[0].metadata["source_hash"] == manifest["sources"][0]["source_hash"]


def test_build_lexical_index_from_manifest_adds_external_test_source(tmp_path):
    pdf = tmp_path / "homework.pdf"
    pdf.write_bytes(b"test pdf bytes")
    derived = tmp_path / "homework.json"
    derived.write_text(
        json.dumps({"content": "kanban homework test content"}),
        encoding="utf-8",
    )
    manifest = _manifest_for(
        pdf,
        course="TEST",
        semester="TEST",
        corpus="test",
        derived_text_path=str(derived),
    )

    index = build_lexical_index_from_manifest(manifest, tmp_path)
    results = index.search("kanban", filters={"course": "TEST", "source_type": "homework"})

    assert len(results) == 1
    assert results[0]["metadata"]["course"] == "TEST"
    assert results[0]["metadata"]["source_hash"] == manifest["sources"][0]["source_hash"]
