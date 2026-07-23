"""Real live end-to-end ingestion for the control-systems test corpus.

This is intentionally an operator script, not a unit test. It runs the local
laptop pipeline, real OpenViking indexing, real Hindsight batching, read-back,
and exact test-resource cleanup. It never targets production course metadata or
hermes-history.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.core.openviking_backend import (  # noqa: E402
    CORNELL_NAMESPACE,
    CornellOpenVikingBackend,
    canonical_resource_root,
    resource_uri,
)
from scripts.ingestion.ingest import ingest_facts  # noqa: E402
from scripts.ops.batch_ingest import BatchItem, run_batch  # noqa: E402
from scripts.ops.ingestion_readback import (  # noqa: E402
    select_readable_source_leaf,
    source_readback_matches,
)
from scripts.ops.laptop_pipeline import run_pipeline  # noqa: E402
from scripts.ops.live_hindsight import LiveHindsightClient  # noqa: E402

CORPUS_PATH = PROJECT_ROOT / "test_runs" / "control_systems_corpus.json"
RUN_ID = time.strftime("%Y%m%d_%H%M%S")
COURSE = f"TEST-CONTROL-SYSTEMS-LIVE-{RUN_ID}"
BANK = f"TEST-CONTROL-SYSTEMS-LIVE-{RUN_ID}"
WORK_DIR = PROJECT_ROOT / "test_runs" / f"control_systems_live_ingestion_{RUN_ID}"
RESULT_PATH = WORK_DIR / "result.json"


def resolve_source(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


class RecordingBackend:
    def __init__(self, backend: CornellOpenVikingBackend) -> None:
        self.backend = backend
        self.responses: list[dict[str, Any]] = []

    @property
    def client(self):
        return self.backend.client

    def index_file(self, path: str, **kwargs: Any):
        resource = self.backend.index_file(path, **kwargs)
        result = resource.result if isinstance(resource.result, dict) else {}
        self.responses.append({
            "source_path": str(path),
            "uri": resource.uri,
            "result_keys": sorted(result),
            "memory_linking_present": "memory_linking" in result,
            "token_usage": result.get("token_usage"),
            "result_status": result.get("status"),
        })
        print(f"[openviking] {len(self.responses)}/22 indexed: {Path(path).name}", flush=True)
        if "memory_linking" in result:
            raise RuntimeError(f"memory_linking appeared in live response for {resource.uri}")
        return resource


def _remove_roots(client: Any, roots: list[str], errors: list[str]) -> None:
    for root in sorted(set(roots), reverse=True):
        try:
            client.rm(root, recursive=True, wait=True)
        except Exception as error:
            errors.append(f"{root}: {type(error).__name__}: {error}")


def main() -> int:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    records = corpus["sources"]
    if len(records) != 22:
        raise AssertionError(f"expected 22 records, got {len(records)}")

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    input_dir = WORK_DIR / "inputs"
    artifact_dir = WORK_DIR / "artifacts"
    input_dir.mkdir(parents=True)
    staged_records: dict[str, dict[str, Any]] = {}

    for record in records:
        source = resolve_source(record["path"])
        if not source.is_file():
            raise FileNotFoundError(f"{record['id']}: {source}")
        staged = input_dir / f"{record['id']}{source.suffix.lower() or '.txt'}"
        shutil.copyfile(source, staged)
        staged_records[str(staged.resolve())] = record

    pipeline_report = run_pipeline(
        input_dir,
        artifact_dir,
        course=COURSE,
        manifest_path=WORK_DIR / "pipeline_manifest.json",
        index=False,
    )
    if len(pipeline_report["items"]) != 22:
        raise AssertionError(f"laptop pipeline produced {len(pipeline_report['items'])} items")

    batch_items: list[BatchItem] = []
    for item in pipeline_report["items"]:
        record = staged_records[str(Path(item["source_path"]).resolve())]
        batch_items.append(BatchItem(
            index_path=Path(item["index_path"]),
            source_path=resolve_source(record["path"]),
            source_hash=item["source_hash"],
            source_type=record["source_type"],
            course=COURSE,
            metadata={
                "source_id": record["id"],
                "family": record.get("family"),
                "role": record.get("role"),
                "semester": "TEST",
                "date": time.strftime("%Y-%m-%d"),
                "corpus": "test",
            },
        ))

    openviking_url = os.environ.get("CORNELL_KB_OPENVIKING_URL", "http://127.0.0.1:1934")
    backend = RecordingBackend(CornellOpenVikingBackend(
        base_url=openviking_url,
        root=PROJECT_ROOT,
        timeout=1800,
    ))
    roots = [canonical_resource_root(resource_uri(
        item.index_path,
        course=COURSE,
        source_type=item.source_type,
        root=PROJECT_ROOT,
        source_hash=item.source_hash,
    )) for item in batch_items]
    hs = LiveHindsightClient()
    batch_report: dict[str, Any] | None = None
    hindsight_report: dict[str, Any] | None = None
    readback: list[dict[str, Any]] = []
    cleanup_errors: list[str] = []
    live_error: str | None = None

    try:
        batch_report = run_batch(
            batch_items,
            backend=backend,
            log_path=WORK_DIR / "index_ingestion.jsonl",
        )
        if batch_report["counts"]["failed"]:
            raise RuntimeError(f"live OpenViking batch had failures: {batch_report}")
        if batch_report["counts"]["indexed"] != 22:
            raise RuntimeError(f"expected 22 live indexed items: {batch_report}")
        if any(row["memory_linking_present"] for row in backend.responses):
            raise RuntimeError("live OpenViking response contained memory_linking")

        for index, (item, root) in enumerate(zip(batch_items, roots), start=1):
            nodes = backend.client.ls(root, recursive=True, node_limit=100) or []
            leaf = select_readable_source_leaf(nodes)
            if leaf is None:
                raise RuntimeError(f"no readable source leaf under {root}")
            content = backend.backend.read(leaf, limit=2000)
            expected = Path(item.index_path).read_text(encoding="utf-8")
            if not source_readback_matches(expected, content):
                raise RuntimeError(f"read-back mismatch for {root}")
            readback.append({"root": root, "leaf": leaf, "content_chars": len(str(content))})
            print(f"[readback] {index}/22 verified: {Path(item.index_path).name}", flush=True)

        facts = []
        for item in batch_items:
            content = Path(item.index_path).read_text(encoding="utf-8")
            facts.append({
                "content": f"{COURSE} {item.metadata['source_id']}: {content[:600]}",
                "course": COURSE,
                "source_type": item.source_type,
                "source_scope": "assessment" if item.source_type in {"homework", "exam"} else "course",
                "topic": item.metadata["family"],
            })
        hindsight_report = ingest_facts(
            facts,
            bank_id=BANK,
            batch_size=5,
            url=hs.base_url,
            client=hs,
        )
        if hindsight_report["success"] != 22 or hindsight_report["failed"]:
            raise RuntimeError(f"live Hindsight batch failed: {hindsight_report}")
        recalled = hs.recall(BANK, COURSE, top_k=3)
        if not recalled.get("results"):
            raise RuntimeError("live Hindsight read-back returned no results")
    except Exception as error:
        live_error = f"{type(error).__name__}: {error}"
    finally:
        _remove_roots(backend.client, roots, cleanup_errors)
        try:
            hs.delete_bank(BANK)
        except Exception as error:
            cleanup_errors.append(f"Hindsight bank {BANK}: {type(error).__name__}: {error}")

    result = {
        "run_id": RUN_ID,
        "course": COURSE,
        "hindsight_bank": BANK,
        "source_count": 22,
        "production_services_accessed": False,
        "live_openviking_url": openviking_url,
        "pipeline_items": len(pipeline_report["items"]),
        "batch_report": batch_report,
        "openviking_response_checks": {
            "responses": len(backend.responses),
            "memory_linking_present": any(row["memory_linking_present"] for row in backend.responses),
            "token_usage_values": [row["token_usage"] for row in backend.responses if row["token_usage"] is not None],
        },
        "readback": readback,
        "hindsight_report": hindsight_report,
        "cleanup_errors": cleanup_errors,
        "live_error": live_error,
        "artifacts": {
            "pipeline_manifest": str(WORK_DIR / "pipeline_manifest.json"),
            "batch_log": str(WORK_DIR / "index_ingestion.jsonl"),
            "result": str(RESULT_PATH),
        },
    }
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "run_id": RUN_ID,
        "live_error": live_error,
        "pipeline_items": len(pipeline_report["items"]),
        "batch": batch_report["counts"] if batch_report else None,
        "responses": len(backend.responses),
        "memory_linking_present": result["openviking_response_checks"]["memory_linking_present"],
        "readback_count": len(readback),
        "hindsight": hindsight_report,
        "cleanup_errors": cleanup_errors,
        "result": str(RESULT_PATH),
    }, indent=2))
    return 0 if live_error is None and not cleanup_errors and len(readback) == 22 else 1


if __name__ == "__main__":
    raise SystemExit(main())
