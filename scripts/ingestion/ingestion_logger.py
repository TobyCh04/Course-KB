"""Structured JSONL ingestion logger for Cornell KB pipeline.

Every index_file / ingest_manifest call can optionally write a timestamped
log line so failures, skips, and successes are auditable without scraping
terminal output.

Usage:
    from scripts.ingestion.ingestion_logger import IngestionLogger

    log = IngestionLogger("logs/ingestion_2026-07-21.jsonl")
    log.record("indexed", uri="viking://...", source_path="/data/ch1.pdf",
               source_hash="abc123...", course="SYSEN 5100", lecture=1)
    log.record("skipped", uri="viking://...", reason="identical_source_hash")
    log.record("error", source_path="/data/bad.pdf", error="SourceHashMismatch")
    log.summary()  # -> {"total": 3, "indexed": 1, "skipped": 1, "error": 1}

The log file is line-delimited JSON, safe for append-only concurrent writers.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LogEntry:
    """One ingest log record."""

    timestamp: str
    status: str  # "indexed", "skipped", "error"
    source_path: str | None = None
    uri: str | None = None
    source_hash: str | None = None
    source_type: str | None = None
    course: str | None = None
    lecture: int | None = None
    reason: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "timestamp": self.timestamp,
            "status": self.status,
        }
        for key in (
            "source_path", "uri", "source_hash", "source_type",
            "course", "lecture", "reason", "error",
        ):
            val = getattr(self, key, None)
            if val is not None:
                d[key] = val
        d.update(self.extra)
        return d


class IngestionLogger:
    """Append-only JSONL ingestion log with in-memory summary."""

    def __init__(self, log_path: str | Path, *, auto_flush: bool = True) -> None:
        self.path = Path(log_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.auto_flush = auto_flush
        self._entries: list[LogEntry] = []
        self._handle = self.path.open("a", encoding="utf-8", buffering=1)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(
        self,
        status: str,
        *,
        source_path: str | None = None,
        uri: str | None = None,
        source_hash: str | None = None,
        source_type: str | None = None,
        course: str | None = None,
        lecture: int | None = None,
        reason: str | None = None,
        error: str | None = None,
        **extra: Any,
    ) -> LogEntry:
        """Write a single log line and return the entry."""
        if status not in ("indexed", "skipped", "error"):
            raise ValueError(
                f"Invalid status {status!r}; must be 'indexed', 'skipped', or 'error'"
            )

        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=status,
            source_path=source_path,
            uri=uri,
            source_hash=source_hash,
            source_type=source_type,
            course=course,
            lecture=lecture,
            reason=reason,
            error=error,
            extra=extra,
        )

        line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
        self._handle.write(line)
        if self.auto_flush:
            self._handle.flush()

        self._entries.append(entry)
        return entry

    def record_indexed(self, resource: Any, **extra: Any) -> LogEntry:
        """Convenience: log a successful IndexedResource."""
        return self.record(
            "indexed",
            source_path=getattr(resource, "source_path", None) or str(resource.get("source_path", "")),
            uri=getattr(resource, "uri", None) or str(resource.get("uri", "")),
            source_type=getattr(resource, "source_type", None) or str(resource.get("source_type", "")),
            course=getattr(resource, "course", None),
            lecture=getattr(resource, "lecture", None),
            **extra,
        )

    def record_skipped(self, uri: str, reason: str, **extra: Any) -> LogEntry:
        """Convenience: log an idempotent skip."""
        return self.record("skipped", uri=uri, reason=reason, **extra)

    def record_error(self, source_path: str, error: str, **extra: Any) -> LogEntry:
        """Convenience: log a failed ingestion."""
        return self.record("error", source_path=source_path, error=error, **extra)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return counts and a summary of the current session."""
        counts = {"total": len(self._entries), "indexed": 0, "skipped": 0, "error": 0}
        errors: list[dict[str, Any]] = []
        for e in self._entries:
            counts[e.status] = counts.get(e.status, 0) + 1
            if e.status == "error" and e.error:
                errors.append({
                    "source_path": e.source_path,
                    "error": e.error,
                    "timestamp": e.timestamp,
                })

        return {
            "log_path": str(self.path),
            "entries": counts,
            "error_count": len(errors),
            "errors": errors,
        }

    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._handle.flush()
        self._handle.close()

    def __enter__(self) -> IngestionLogger:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------


def read_logged_uris(log_path: str | Path) -> set[str]:
    """Read a JSONL log and return the set of successfully indexed URIs.

    Use this to skip already-indexed resources on resume.
    """
    path = Path(log_path).expanduser()
    if not path.is_file():
        return set()

    uris: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("status") == "indexed" and entry.get("uri"):
                uris.add(entry["uri"])
    return uris


def build_resume_manifest(
    source_manifest: str | Path | dict[str, Any],
    log_path: str | Path,
) -> dict[str, Any]:
    """Return a manifest with already-indexed entries filtered out.

    Reads the log, extracts indexed URIs, and removes matching manifest
    entries so that a re-run of ingest_manifest only processes remaining
    sources.
    """
    indexed_uris = read_logged_uris(log_path)
    if not indexed_uris:
        if isinstance(source_manifest, dict):
            return source_manifest
        return json.loads(Path(source_manifest).read_text(encoding="utf-8"))

    from scripts.core.openviking_backend import CORNELL_NAMESPACE

    if isinstance(source_manifest, dict):
        data = source_manifest
    else:
        data = json.loads(Path(source_manifest).read_text(encoding="utf-8"))

    sources = data.get("sources", [])
    if not sources:
        return data

    # Filter: keep only entries whose expected URI is NOT already logged.
    remaining = []
    skipped = 0
    for entry in sources:
        sp = entry.get("source_path", "")
        sh = entry.get("source_hash", "")
        if sh and sp:
            # The digest in the URI is a 12-char hex prefix of SHA-256.
            # Also match by source stem to catch path changes.
            stem = Path(sp).stem
            already = any(
                stem in u or (sh[:12] in u)
                for u in indexed_uris
            )
            if already:
                skipped += 1
                continue
        remaining.append(entry)

    data["sources"] = remaining
    data["_resume_from_log"] = str(log_path)
    data["_skipped_from_log"] = skipped
    return data
