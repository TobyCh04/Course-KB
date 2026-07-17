"""Safe OpenViking adapter for Cornell KB source resources.

Audio is an input to transcription, never an OpenViking resource.  The adapter
accepts the resulting transcript (plus supported document/text artifacts), uses
deterministic resource URIs for idempotent re-indexing, and keeps the OpenViking
client injectable so tests never contact the live service.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

CORNELL_NAMESPACE = "viking://resources/cornell-kb"
DEFAULT_OPENVIKING_URL = "http://127.0.0.1:1934"

AUDIO_EXTENSIONS = frozenset({
    ".aac", ".aiff", ".flac", ".m4a", ".mka", ".mp3", ".ogg", ".opus", ".wav", ".wma"
})
SUPPORTED_EXTENSIONS = frozenset({
    ".csv", ".json", ".md", ".markdown", ".pdf", ".tex", ".txt", ".yaml", ".yml"
})
RAW_BOOK_FILENAMES = frozenset({"full_text.txt", "lean-implementation-tools.pdf"})

# The default Cornell namespace is a curated study corpus, not a mirror of the
# project repository. Keep this allowlist explicit so scripts, plans,
# benchmarks, raw books, duplicate exports, and infrastructure notes cannot be
# indexed accidentally.
CURATED_SOURCE_PATHS = frozenset({
    "config/course_catalog.yaml",
    "data/freq_response_diagrams.json",
    "data/freq_response_part2.json",
})
CURATED_DERIVED_ROOT = Path("books/lean-implementation")
CURATED_DERIVED_EXCLUDED_PARTS = frozenset({"candidates"})
CURATED_DERIVED_EXTENSIONS = frozenset({".md", ".markdown"})


class OpenVikingClient(Protocol):
    def add_resource(self, **kwargs: Any) -> Any: ...

    def search(self, **kwargs: Any) -> Any: ...

    def read(self, uri: str, **kwargs: Any) -> Any: ...


class AudioSourceRejected(ValueError):
    """Raised when an audio file is about to be sent to OpenViking."""


class UnsupportedSource(ValueError):
    """Raised for files that are not approved Cornell KB source artifacts."""


@dataclass(frozen=True)
class IndexedResource:
    """The safe, auditable description of one indexing operation."""

    source_path: str
    uri: str
    source_type: str
    course: str | None
    lecture: int | None
    metadata: dict[str, Any]
    result: Any = None


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return value or "unnamed"


def is_audio_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def validate_source_path(path: str | Path) -> Path:
    """Validate a source without reading or uploading it."""
    source = Path(path).expanduser()
    if is_audio_path(source):
        raise AudioSourceRejected(
            f"Audio is local-only and must be transcribed before OpenViking ingestion: {source}"
        )
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedSource(
            f"Unsupported Cornell KB source type {source.suffix or '<none>'}: {source}"
        )
    if not source.is_file():
        raise FileNotFoundError(source)
    return source.resolve()


def resource_uri(
    source: str | Path,
    *,
    course: str | None = None,
    source_type: str = "source",
    root: str | Path | None = None,
) -> str:
    """Build a deterministic URI without exposing unrelated absolute paths."""
    path = Path(source).expanduser().resolve()
    base = Path(root).expanduser().resolve() if root else path.parent
    try:
        display_path = path.relative_to(base).as_posix()
    except ValueError:
        display_path = path.name
    identity = "/".join(part for part in (course, source_type, display_path) if part)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    parts = [_slug(course or "uncategorized"), _slug(source_type), _slug(path.stem)]
    return f"{CORNELL_NAMESPACE}/{'/'.join(parts)}-{digest}"


class CornellOpenVikingBackend:
    """Index and retrieve Cornell source artifacts through OpenViking."""

    def __init__(
        self,
        client: OpenVikingClient | None = None,
        *,
        base_url: str = DEFAULT_OPENVIKING_URL,
        root: str | Path | None = None,
        timeout: float = 1800,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.root = Path(root).expanduser().resolve() if root else None
        self.timeout = timeout
        self._client = client

    @property
    def client(self) -> OpenVikingClient:
        if self._client is None:
            try:
                from openviking_sdk import SyncHTTPClient
            except ImportError as error:  # pragma: no cover - environment dependent
                raise RuntimeError(
                    "openviking_sdk is required for live indexing; inject a client for tests"
                ) from error
            self._client = SyncHTTPClient(url=self.base_url, timeout=self.timeout)
            self._client.initialize()
        return self._client

    def index_file(
        self,
        source: str | Path,
        *,
        source_type: str,
        course: str | None = None,
        lecture: int | None = None,
        metadata: dict[str, Any] | None = None,
        dry_run: bool = False,
    ) -> IndexedResource:
        path = validate_source_path(source)
        safe_metadata = _safe_metadata(metadata)
        safe_metadata.update({
            "course": course,
            "lecture": lecture,
            "source_type": source_type,
        })
        safe_metadata = {key: value for key, value in safe_metadata.items() if value is not None}
        uri = resource_uri(path, course=course, source_type=source_type, root=self.root)
        if dry_run:
            return IndexedResource(str(path), uri, source_type, course, lecture, safe_metadata)

        # Only the validated transcript/document path is passed to OpenViking.
        # In particular, no source audio path or audio bytes are ever included.
        result = self.client.add_resource(
            path=str(path),
            to=uri,
            wait=True,
            timeout=self.timeout,
            reason=_reason(source_type, course, lecture),
            preserve_structure=True,
        )
        return IndexedResource(str(path), uri, source_type, course, lecture, safe_metadata, result)

    def index_tree(
        self,
        root: str | Path,
        *,
        course: str | None = None,
        source_type: str = "source",
        dry_run: bool = False,
    ) -> list[IndexedResource]:
        """Index approved files below root; silently skip audio and generated debris."""
        base = Path(root).expanduser().resolve()
        if not base.is_dir():
            raise NotADirectoryError(base)
        backend = self if self.root is not None else CornellOpenVikingBackend(
            self._client, base_url=self.base_url, root=base, timeout=self.timeout
        )
        resources: list[IndexedResource] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file() or not is_approved_cornell_path(path, base):
                continue
            resources.append(
                backend.index_file(
                    path,
                    source_type=source_type,
                    course=course,
                    dry_run=dry_run,
                )
            )
        return resources

    def search(self, query: str, *, target_uri: str = "", limit: int = 8) -> Any:
        _check_namespace(target_uri or CORNELL_NAMESPACE)
        return self.client.search(
            query=query,
            target_uri=target_uri or CORNELL_NAMESPACE,
            limit=max(1, min(int(limit), 20)),
        )

    def read(self, uri: str, *, limit: int = 20000) -> Any:
        _check_namespace(uri)
        return self.client.read(uri, offset=0, limit=max(1, min(int(limit), 50000)))


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    # Do not allow an audio path or binary payload to enter metadata accidentally.
    safe = {}
    for key, value in metadata.items():
        key_text = str(key).lower()
        if "audio" in key_text or key_text in {"audio_path", "audio_file", "audio_bytes"}:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[str(key)] = value
    return safe


def _reason(source_type: str, course: str | None, lecture: int | None) -> str:
    details = ["Cornell KB source ingestion", source_type]
    if course:
        details.append(course)
    if lecture is not None:
        details.append(f"lecture {lecture}")
    return " — ".join(details)


def _ignored_path(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    normalized_parts = {part.lower() for part in relative_parts}
    if normalized_parts & {
        ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
        ".venv", "venv", "test_runs", "test_models", "tests", "test",
    }:
        return True
    name = path.name.lower()
    if name.startswith(("test_", "test-")) or name in {"test.m4a", "test.txt"}:
        return True
    return name in RAW_BOOK_FILENAMES


def is_approved_cornell_path(path: str | Path, root: str | Path) -> bool:
    """Return whether a file belongs in the curated Cornell study namespace."""
    candidate = Path(path).expanduser().resolve()
    base = Path(root).expanduser().resolve()
    if not candidate.is_file():
        return False
    try:
        relative = candidate.relative_to(base)
    except ValueError:
        return False
    if _ignored_path(candidate, base):
        return False
    if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False
    if relative.as_posix() in CURATED_SOURCE_PATHS:
        return True
    if (
        relative.parts[:2] == CURATED_DERIVED_ROOT.parts
        and candidate.suffix.lower() in CURATED_DERIVED_EXTENSIONS
        and not (set(relative.parts) & CURATED_DERIVED_EXCLUDED_PARTS)
    ):
        return True
    return False


def _check_namespace(uri: str) -> None:
    if not uri.startswith(CORNELL_NAMESPACE):
        raise ValueError("OpenViking URI is outside the Cornell KB namespace")


__all__ = [
    "AUDIO_EXTENSIONS",
    "CORNELL_NAMESPACE",
    "CornellOpenVikingBackend",
    "AudioSourceRejected",
    "IndexedResource",
    "SUPPORTED_EXTENSIONS",
    "RAW_BOOK_FILENAMES",
    "CURATED_SOURCE_PATHS",
    "CURATED_DERIVED_ROOT",
    "is_approved_cornell_path",
    "UnsupportedSource",
    "is_audio_path",
    "resource_uri",
    "validate_source_path",
]
