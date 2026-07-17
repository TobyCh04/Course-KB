"""Cornell KB source-grounded retrieval CLI — /search, /source, /trace.

Usage:
    python scripts/search.py search "feedback stability"
    python scripts/search.py search "kanban" --limit 5
    python scripts/search.py source "viking://resources/cornell-kb/.../SKILL-abc123"
    python scripts/search.py trace "closed-loop transfer function"
    python scripts/search.py health

quires the OpenViking SDK (openviking_sdk) and a running OpenViking server
default port 1934. All search/read operations are namespace-locked to
ng://resources/cornell-kb.
   _ __ 
  | '_ |
  | .__| 
  |_|    ions are returned as JSON to stdout for programmatic use.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:
    from .openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE
except ImportError:  # pragma: no cover - exercised by direct CLI use
    from openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE

DEFAULT_OPENVIKING_URL = "http://127.0.0.1:1934"
DEFAULT_LIMIT = 8


def _get_backend(base_url: str, timeout: float) -> CornellOpenVikingBackend:
    """Create a backend with the real OpenViking SDK client (lazy-loaded)."""
    return CornellOpenVikingBackend(base_url=base_url, timeout=timeout)


def cmd_search(backend: CornellOpenVikingBackend, query: str, limit: int) -> dict[str, Any]:
    """Search the Cornell namespace and return ranked results with abstracts."""
    raw = backend.search(query, limit=limit)
    results = []
    for hit in raw.get("resources", []):
        results.append({
            "uri": hit.get("uri", ""),
            "score": round(hit.get("score", 0.0), 4),
            "level": hit.get("level", 0),
            "abstract": (hit.get("abstract") or "")[:500],
        })
    return {
        "query": query,
        "namespace": CORNELL_NAMESPACE,
        "total": raw.get("total", len(results)),
        "results": results,
    }


def cmd_source(backend: CornellOpenVikingBackend, uri: str, read_limit: int) -> dict[str, Any]:
    """Read the full source content at a specific OpenViking URI."""
    content = backend.read(uri, limit=read_limit)
    return {
        "uri": uri,
        "content": content,
    }


def cmd_trace(backend: CornellOpenVikingBackend, query: str, limit: int) -> dict[str, Any]:
    """Search + read: return the search results plus the top result's full source."""
    search_result = cmd_search(backend, query, limit)
    if search_result["results"]:
        top_uri = search_result["results"][0]["uri"]
        source = cmd_source(backend, top_uri, read_limit=10000)
        search_result["top_source"] = {
            "uri": top_uri,
            "content": (source["content"] or "")[:2000],
        }
    return search_result


def cmd_health(backend: CornellOpenVikingBackend) -> dict[str, Any]:
    """Check OpenViking server health and namespace accessibility."""
    try:
        # Force lazy client init — will raise if SDK missing or server unreachable.
        client = backend.client
        # SyncHTTPClient.health() returns dict or falsy; bool() it for status.
        raw_health = client.health()
        is_healthy = bool(raw_health) if not isinstance(raw_health, dict) else raw_health.get("healthy", True)
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "url": backend.base_url,
            "namespace": CORNELL_NAMESPACE,
            "health": raw_health,
        }
    except Exception as exc:
        return {
            "status": "error",
            "url": backend.base_url,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="search",
        description="Cornell KB source-grounded retrieval via OpenViking",
    )
    parser.add_argument(
        "command",
        choices=["search", "source", "trace", "health"],
        help="search: query the index | source: read a URI | trace: search+read top hit | health: check server",
    )
    parser.add_argument("query", nargs="?", help="Search query or source URI")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max results (search/trace)")
    parser.add_argument("--read-limit", type=int, default=20000, help="Max chars to read (source)")
    parser.add_argument("--url", default=DEFAULT_OPENVIKING_URL, help="OpenViking server URL")
    parser.add_argument("--timeout", type=float, default=30, help="Request timeout in seconds")
    args = parser.parse_args()

    if args.command in ("search", "source", "trace") and not args.query:
        parser.error(f"{args.command} requires a query or URI argument")

    backend = _get_backend(args.url, args.timeout)

    if args.command == "health":
        result = cmd_health(backend)
    elif args.command == "search":
        result = cmd_search(backend, args.query, args.limit)
    elif args.command == "source":
        result = cmd_source(backend, args.query, args.read_limit)
    elif args.command == "trace":
        result = cmd_trace(backend, args.query, args.limit)
    else:
        parser.error(f"Unknown command: {args.command}")
        return 2

    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())