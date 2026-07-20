"""Safe OpenViking adapter for Cornell KB source resources.

Audio is an input to transcription, never an OpenViking resource.  The adapter
accepts the resulting transcript (plus supported document/text artifacts), uses
deterministic resource URIs for idempotent re-indexing, and keeps the OpenViking
client injectable so tests never contact the live service.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
METADATA_FILTER_KEYS = frozenset({"course", "lecture", "source_type", "source_scope", "semester", "date"})
SOURCE_SCOPES = frozenset({"course", "assessment", "all"})


def validate_metadata_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and copy the finite metadata filter contract."""
    if not filters:
        return {}
    unknown = set(filters) - METADATA_FILTER_KEYS
    if unknown:
        raise ValueError(f"unsupported metadata filters: {sorted(unknown)}")
    normalized: dict[str, Any] = {}
    for key, value in filters.items():
        if key == "lecture":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 1000:
                raise ValueError("lecture filter must be an integer between 1 and 1000")
            normalized[key] = value
        elif key == "source_scope":
            if value not in SOURCE_SCOPES:
                raise ValueError(f"unsupported source_scope: {value}")
            normalized[key] = value
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} filter must be non-empty text")
            normalized[key] = value.strip()
    return normalized


def metadata_matches(metadata: dict[str, Any] | None, filters: dict[str, Any] | None) -> bool:
    """Return whether one source metadata record satisfies all filters."""
    normalized = validate_metadata_filters(filters)
    if not normalized:
        return True
    actual = metadata or {}
    for key, expected in normalized.items():
        if key == "source_scope":
            raw_type = actual.get("source_type")
            if raw_type is None:
                return False
            actual_type = "source" if str(raw_type).casefold() == "cornell-source" else str(raw_type).casefold()
            if expected == "course" and actual_type in {"homework", "exam"}:
                return False
            if expected == "assessment" and actual_type not in {"homework", "exam"}:
                return False
            continue
        value = actual.get(key)
        if value is None:
            return False
        if key == "lecture":
            try:
                if int(value) != expected:
                    return False
            except (TypeError, ValueError):
                return False
        elif key == "course":
            actual_course = "".join(char for char in str(value).casefold() if char.isalnum())
            expected_course = "".join(char for char in expected.casefold() if char.isalnum())
            if actual_course != expected_course:
                return False
        elif key == "source_type":
            actual_type = "source" if str(value).casefold() == "cornell-source" else str(value)
            if actual_type.casefold() != expected.casefold():
                return False
        elif str(value).casefold() != expected.casefold():
            return False
    return True


def resource_metadata(resource: dict[str, Any]) -> dict[str, Any]:
    """Merge supported metadata fields from nested, flat, and URI shapes."""
    metadata = dict(resource.get("metadata") or {})
    for key in METADATA_FILTER_KEYS:
        if key in resource and key not in metadata:
            metadata[key] = resource[key]
    uri = str(resource.get("uri", ""))
    if uri.startswith(CORNELL_NAMESPACE + "/"):
        parts = uri.removeprefix(CORNELL_NAMESPACE + "/").split("/")
        if len(parts) >= 2:
            if parts[0] != "uncategorized":
                metadata.setdefault("course", parts[0].replace("-", " "))
            metadata.setdefault(
                "source_type",
                "source" if parts[1] == "cornell-source" else parts[1],
            )
    return metadata


class OpenVikingClient(Protocol):
    def add_resource(self, **kwargs: Any) -> Any: ...

    def search(self, **kwargs: Any) -> Any: ...

    def read(self, uri: str, **kwargs: Any) -> Any: ...

    def ls(self, uri: str, **kwargs: Any) -> Any: ...


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
    source_hash: str | None = None,
) -> str:
    """Build a deterministic URI without exposing unrelated absolute paths.

    When an authoritative source hash is available, include it in the identity
    so changed content at the same path cannot silently reuse the old resource.
    Legacy callers without a hash retain the historical path-based identity.
    """
    path = Path(source).expanduser().resolve()
    base = Path(root).expanduser().resolve() if root else path.parent
    try:
        display_path = path.relative_to(base).as_posix()
    except ValueError:
        display_path = path.name
    identity_parts = [part for part in (course, source_type, display_path) if part]
    if source_hash:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", source_hash):
            raise ValueError("source_hash must be a full 64-character SHA-256")
        identity_parts.append(source_hash.casefold())
    identity = "/".join(identity_parts)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    parts = [_slug(course or "uncategorized"), _slug(source_type), _slug(path.stem)]
    return f"{CORNELL_NAMESPACE}/{'/'.join(parts)}-{digest}"


def canonical_resource_root(uri: str) -> str:
    """Return the manifest-addressable resource root for a leaf URI."""
    prefix = CORNELL_NAMESPACE + "/"
    if not uri.startswith(prefix):
        return uri
    parts = uri.removeprefix(prefix).split("/")
    return prefix + "/".join(parts[:3]) if len(parts) >= 3 else uri


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
        self._uri_repair_cache: dict[str, str | None] = {}
        self._resource_files_cache: list[dict[str, Any]] | None = None
        self._manifest_metadata = self._load_manifest_metadata()

    def _load_manifest_metadata(self) -> dict[str, dict[str, Any]]:
        if self.root is None:
            return {}
        manifest_path = self.root / "config" / "source_manifest.json"
        if not manifest_path.is_file():
            return {}
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        metadata_by_root: dict[str, dict[str, Any]] = {}
        for entry in data.get("sources", []):
            if not isinstance(entry, dict) or not entry.get("source_path"):
                continue
            path = Path(str(entry["source_path"])).expanduser()
            if not path.is_absolute():
                path = self.root / path
            # ``resource_uri`` validates the source hash shape when one is
            # present; a malformed manifest entry must not crash backend
            # construction (search/filter callers depend on this tolerant
            # loader).  ``validate_manifest`` remains the authoritative gate
            # for ingestion; here we simply skip unparseable entries.
            try:
                uri = resource_uri(
                    path,
                    course=entry.get("course"),
                    source_type=entry.get("source_type", "source"),
                    root=self.root,
                    source_hash=entry.get("source_hash"),
                )
            except ValueError:
                continue
            metadata_by_root[canonical_resource_root(uri)] = {
                key: entry[key]
                for key in (
                    "course",
                    "lecture",
                    "source_type",
                    "semester",
                    "date",
                    "corpus",
                    "source_hash",
                )
                if entry.get(key) is not None
            }
        return metadata_by_root

    def _metadata_for_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        metadata = resource_metadata(resource)
        manifest_metadata = self._manifest_metadata.get(
            canonical_resource_root(str(resource.get("uri", ""))),
            {},
        )
        metadata.update(manifest_metadata)
        return metadata

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
        source_hash: str | None = None,
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
        uri = resource_uri(
            path,
            course=course,
            source_type=source_type,
            root=self.root,
            source_hash=source_hash,
        )
        if dry_run:
            return IndexedResource(str(path), uri, source_type, course, lecture, safe_metadata)

        # Build provenance metadata.  The source hash (when supplied by the
        # caller) is embedded in the ``args`` payload so every resource carries
        # its own audit trail regardless of the manifest.
        provenance = _provenance_args(
            safe_metadata,
            course=course,
            lecture=lecture,
            source_type=source_type,
            source_hash=source_hash,
            source_path=str(path),
        )

        # Only the validated transcript/document path is passed to OpenViking.
        # In particular, no source audio path or audio bytes are ever included.
        # ``reason`` is deliberately empty to prevent server-side memory linking.
        result = self.client.add_resource(
            path=str(path),
            to=uri,
            wait=True,
            timeout=self.timeout,
            reason="",
            args=provenance,
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

    def _resource_files(self) -> list[dict[str, Any]]:
        """Cache readable file nodes from the live Cornell tree for URI repair."""
        if self._resource_files_cache is not None:
            return self._resource_files_cache
        files: list[dict[str, Any]] = []
        try:
            roots = self.client.ls(CORNELL_NAMESPACE, recursive=True, node_limit=2000)
            for root in roots or []:
                if not root.get("isDir") or not root.get("uri"):
                    continue
                children = self.client.ls(root["uri"], recursive=True, node_limit=2000)
                for item in children or []:
                    if not item.get("isDir") and item.get("uri"):
                        files.append(item)
        except Exception:
            files = []
        # De-duplicate tree entries returned by different SDK traversal modes.
        unique: dict[str, dict[str, Any]] = {item["uri"]: item for item in files}
        self._resource_files_cache = list(unique.values())
        return self._resource_files_cache

    def resolve_uri(self, uri: str) -> str | None:
        """Resolve stale filename-only search URIs to a canonical readable child URI."""
        _check_namespace(uri)
        if uri in self._uri_repair_cache:
            return self._uri_repair_cache[uri]
        requested_name = uri.rsplit("/", 1)[-1].casefold()
        requested_stem = requested_name.rsplit(".", 1)[0]
        files = self._resource_files()
        exact = [
            item["uri"] for item in files
            if str(item.get("name", "")).casefold() == requested_name
        ]
        stem_matches = [
            item["uri"] for item in files
            if str(item.get("name", "")).casefold().rsplit(".", 1)[0] == requested_stem
        ]
        prefix_matches = [
            item["uri"] for item in files
            if str(item.get("name", "")).casefold().rsplit(".", 1)[0].startswith(requested_stem)
        ]
        repaired = next(iter(exact or stem_matches or prefix_matches), None)
        self._uri_repair_cache[uri] = repaired
        return repaired

    def search(
        self,
        query: str,
        *,
        target_uri: str = "",
        limit: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> Any:
        _check_namespace(target_uri or CORNELL_NAMESPACE)
        normalized_filters = validate_metadata_filters(filters)
        raw = self.client.search(
            query=query,
            target_uri=target_uri or CORNELL_NAMESPACE,
            limit=max(1, min(int(limit), 20)),
        )
        if not normalized_filters:
            return raw
        filtered = dict(raw)
        resources = [
            resource for resource in raw.get("resources", [])
            if metadata_matches(self._metadata_for_resource(resource), normalized_filters)
        ]
        filtered["resources"] = resources
        filtered["total"] = len(resources)
        filtered["filters_applied"] = normalized_filters
        return filtered

    def read(self, uri: str, *, limit: int = 20000) -> Any:
        _check_namespace(uri)
        try:
            return self.client.read(uri, offset=0, limit=max(1, min(int(limit), 50000)))
        except Exception:
            repaired = self.resolve_uri(uri)
            if repaired and repaired != uri:
                return self.client.read(repaired, offset=0, limit=max(1, min(int(limit), 50000)))
            raise

    def hybrid_search(
        self,
        query: str,
        *,
        index_path: str | Path = "data/lexical_index.json",
        search_limit: int = 20,
        lexical_limit: int = 20,
        top_k: int = 10,
        **kwargs: Any,
    ) -> Any:
        """Dense + BM25 lexical hybrid search with optional reranking.

        This is a thin wrapper that delegates to hybrid_retrieval to avoid a
        circular module dependency at import time.
        """
        try:
            from . import hybrid_retrieval
        except ImportError:  # pragma: no cover - direct CLI use
            import hybrid_retrieval
        return hybrid_retrieval.hybrid_search(
            self,
            query,
            index_path=Path(index_path),
            search_limit=search_limit,
            lexical_limit=lexical_limit,
            top_k=top_k,
            **kwargs,
        )


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


def _provenance_args(
    metadata: dict[str, Any] | None = None,
    *,
    course: str | None = None,
    lecture: int | None = None,
    source_type: str,
    source_hash: str | None = None,
    source_path: str | None = None,
) -> dict[str, Any]:
    """Build a structured provenance payload for OpenViking ``args``.

    Every Cornell KB resource stores its audit trail alongside the document so
    downstream consumers can verify source identity without relying on a
    separate manifest lookup.
    """
    provenance: dict[str, Any] = {
        "cornell_kb_processor_version": "1.0.0",
        "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_type": source_type,
    }
    if source_hash:
        provenance["source_hash"] = source_hash
    if source_path:
        provenance["provenance_source_path"] = source_path
    if course:
        provenance["course"] = course
    if lecture is not None:
        provenance["lecture"] = lecture
    if metadata:
        for key in ("semester", "date", "corpus"):
            if metadata.get(key) is not None:
                provenance[key] = metadata[key]
    return provenance


def _reason(
    source_type: str,
    course: str | None,
    lecture: int | None,
    metadata: dict[str, Any] | None = None,
) -> str:
    details = ["Cornell KB source ingestion", f"source_type={source_type}"]
    if course:
        details.append(f"course={course}")
    if lecture is not None:
        details.append(f"lecture {lecture}")
    if metadata:
        for key in ("semester", "date", "corpus", "source_hash"):
            if metadata.get(key) is not None:
                details.append(f"{key}={metadata[key]}")
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
    if uri != CORNELL_NAMESPACE and not uri.startswith(CORNELL_NAMESPACE + "/"):
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
    "_provenance_args",
]
