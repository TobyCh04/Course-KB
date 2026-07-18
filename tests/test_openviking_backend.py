import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.openviking_backend import (  # noqa: E402
    CORNELL_NAMESPACE,
    AudioSourceRejected,
    CornellOpenVikingBackend,
    is_approved_cornell_path,
    resource_uri,
)


class FakeOpenVikingClient:
    def __init__(self, search_response=None):
        self.add_calls = []
        self.search_calls = []
        self.read_calls = []
        self.search_response = search_response or {"resources": []}

    def add_resource(self, **kwargs):
        self.add_calls.append(kwargs)
        return {"uri": kwargs["to"], "status": "completed"}

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.search_response

    def read(self, uri, **kwargs):
        self.read_calls.append((uri, kwargs))
        return "transcript context"


def test_audio_is_rejected_before_client_call(tmp_path):
    audio = tmp_path / "lecture.m4a"
    audio.write_bytes(b"audio bytes")
    client = FakeOpenVikingClient()
    backend = CornellOpenVikingBackend(client, root=tmp_path)

    with pytest.raises(AudioSourceRejected, match="local-only"):
        backend.index_file(audio, source_type="lecture-audio", course="SYSEN 5100")

    assert client.add_calls == []


def test_transcript_is_indexed_without_audio_metadata(tmp_path):
    transcript = tmp_path / "lecture_01.txt"
    transcript.write_text("The closed-loop transfer function is important.", encoding="utf-8")
    client = FakeOpenVikingClient()
    backend = CornellOpenVikingBackend(client, root=tmp_path)

    resource = backend.index_file(
        transcript,
        source_type="transcript",
        course="SYSEN 5100",
        lecture=1,
        metadata={"engine": "whisper", "audio_path": str(tmp_path / "lecture_01.m4a")},
    )

    assert resource.uri.startswith(CORNELL_NAMESPACE)
    assert len(client.add_calls) == 1
    call = client.add_calls[0]
    assert call["path"] == str(transcript.resolve())
    assert call["to"] == resource.uri
    assert "m4a" not in repr(call).lower()
    assert resource.metadata == {
        "engine": "whisper",
        "course": "SYSEN 5100",
        "lecture": 1,
        "source_type": "transcript",
    }


def test_dry_run_validates_transcript_without_uploading(tmp_path):
    transcript = tmp_path / "lecture.md"
    transcript.write_text("A transcript with enough content for validation.", encoding="utf-8")
    client = FakeOpenVikingClient()
    backend = CornellOpenVikingBackend(client, root=tmp_path)

    resource = backend.index_file(transcript, source_type="transcript", dry_run=True)

    assert resource.result is None
    assert resource.uri.startswith(CORNELL_NAMESPACE)
    assert client.add_calls == []


def test_tree_applies_curated_policy_and_skips_unapproved_files(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "course_catalog.yaml").write_text("courses: {}", encoding="utf-8")
    derived = tmp_path / "books" / "lean-implementation" / "house-of-lean"
    derived.mkdir(parents=True)
    (derived / "SKILL.md").write_text("final derived study note", encoding="utf-8")
    candidates = tmp_path / "books" / "lean-implementation" / "candidates"
    candidates.mkdir(parents=True)
    (candidates / "draft.md").write_text("candidate draft", encoding="utf-8")
    (tmp_path / "lecture.txt").write_text("lecture transcript", encoding="utf-8")
    (tmp_path / "full_text.txt").write_text("raw book extraction", encoding="utf-8")
    (tmp_path / "test_models").mkdir()
    (tmp_path / "test_models" / "fixture.txt").write_text("fixture", encoding="utf-8")
    client = FakeOpenVikingClient()
    backend = CornellOpenVikingBackend(client, root=tmp_path)

    resources = backend.index_tree(tmp_path, source_type="cornell-source", dry_run=True)

    assert {Path(item.source_path).name for item in resources} == {"course_catalog.yaml", "SKILL.md"}
    assert len(resources) == 2
    assert client.add_calls == []
    assert is_approved_cornell_path(config / "course_catalog.yaml", tmp_path)
    assert not is_approved_cornell_path(tmp_path / "lecture.txt", tmp_path)
    assert not is_approved_cornell_path(candidates / "draft.md", tmp_path)

def test_resource_uri_is_deterministic_for_idempotent_reingestion(tmp_path):
    source = tmp_path / "lecture.txt"

    first = resource_uri(source, course="SYSEN 5100", source_type="transcript", root=tmp_path)
    second = resource_uri(source, course="SYSEN 5100", source_type="transcript", root=tmp_path)

    assert first == second
    assert first.startswith(CORNELL_NAMESPACE + "/")


def test_search_and_read_are_limited_to_cornell_namespace():
    client = FakeOpenVikingClient()
    backend = CornellOpenVikingBackend(client)

    backend.search("feedback", limit=3)
    backend.read(CORNELL_NAMESPACE + "/transcript/lecture-abc")

    with pytest.raises(ValueError, match="outside the Cornell KB namespace"):
        backend.read("viking://resources/other")


def test_namespace_prefix_collision_is_rejected():
    client = FakeOpenVikingClient()
    backend = CornellOpenVikingBackend(client)

    with pytest.raises(ValueError, match="outside the Cornell KB namespace"):
        backend.read(CORNELL_NAMESPACE + "-unauthorized/resource")
