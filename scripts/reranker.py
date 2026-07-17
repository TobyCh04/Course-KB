"""Cross-encoder reranking layer for Cornell KB retrieval.

Retrieves a broad candidate set from OpenViking dense search, then applies a
stronger cross-encoder to reorder the top candidates. Falls back to dense
ranking if the reranker is unavailable or times out.

Usage:
    # In-process (loads model each call, ~19s overhead)
    python scripts/reranker.py search "feedback stability" --limit 20 --rerank-top 5
    python scripts/reranker.py ab "kanban" --limit 20  # A/B comparison

    # Server mode (model loaded once, <1s per query):
    #   1. Start the server:  python scripts/reranker_server.py --port 1940
    #   2. Use with --server: python scripts/reranker.py search "kanban" --server localhost:1940

Default model: BAAI/bge-reranker-base (local, ~278MB, CPU-compatible).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from .openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE
except ImportError:  # pragma: no cover
    from openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE

DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-base"
DEFAULT_OPENVIKING_URL = "http://127.0.0.1:1934"
DEFAULT_SEARCH_LIMIT = 20
DEFAULT_RERANK_TOP = 5
DEFAULT_RERANKER_SERVER = ""  # empty = in-process; set to "host:port" for server mode

# Module-level cache so the model loads once per process.
_reranker_model: Any = None
_reranker_model_name: str | None = None


def _get_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> Any:
    """Lazy-load the cross-encoder model, cached per process."""
    global _reranker_model, _reranker_model_name
    if _reranker_model is not None and _reranker_model_name == model_name:
        return _reranker_model
    from sentence_transformers import CrossEncoder
    _reranker_model = CrossEncoder(model_name)
    _reranker_model_name = model_name
    return _reranker_model


def _rerank_via_server(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    server_url: str,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """Rerank by POSTing candidates to the persistent reranker server."""
    payload = json.dumps({
        "query": query,
        "candidates": candidates,
        "top_k": top_k,
    }, ensure_ascii=False).encode("utf-8")

    url = f"http://{server_url.rstrip('/')}/rerank"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])
        latency = data.get("latency_ms")
        if latency is not None:
            # Attach server-side latency for the caller to use.
            for r in results:
                r.setdefault("_server_latency_ms", latency)
        return results
    except Exception:
        # Fallback to dense ranking if server is unreachable.
        return sorted(candidates, key=lambda c: c.get("score", 0.0), reverse=True)[:top_k]


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    model_name: str = DEFAULT_RERANKER_MODEL,
    top_k: int = DEFAULT_RERANK_TOP,
    timeout_seconds: float = 30.0,
    server_url: str = "",
) -> list[dict[str, Any]]:
    """Rerank OpenViking search results with a cross-encoder.

    Args:
        query: The original search query.
        candidates: List of search result dicts with 'uri', 'score', 'abstract'.
        model_name: HuggingFace cross-encoder model name (in-process mode only).
        top_k: Number of results to return after reranking.
        timeout_seconds: If reranking exceeds this, fall back to dense ranking.
        server_url: If non-empty, use the persistent reranker server instead of
            loading the model in-process (e.g. "localhost:1940").

    Returns:
        Reranked list of top_k candidates with added 'rerank_score' field.
    """
    if not candidates:
        return []

    if len(candidates) <= top_k:
        # No point reranking if we already have fewer than top_k results.
        return candidates

    # Server mode: delegate to the persistent reranker server.
    if server_url:
        return _rerank_via_server(query, candidates, top_k, server_url, timeout_seconds)

    # In-process mode: load the model and score locally.
    try:
        model = _get_reranker(model_name)
        # Build (query, document) pairs for the cross-encoder.
        pairs = [(query, c.get("abstract", "") or c.get("uri", "")) for c in candidates]
        scores = model.predict(pairs)

        # Attach rerank scores and sort.
        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = float(score)
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        return candidates[:top_k]

    except Exception:
        # Fallback: return the top-k by original dense score.
        return sorted(candidates, key=lambda c: c.get("score", 0.0), reverse=True)[:top_k]


def search_with_rerank(
    backend: CornellOpenVikingBackend,
    query: str,
    *,
    search_limit: int = DEFAULT_SEARCH_LIMIT,
    rerank_top: int = DEFAULT_RERANK_TOP,
    model_name: str = DEFAULT_RERANKER_MODEL,
    use_reranker: bool = True,
    server_url: str = "",
) -> dict[str, Any]:
    """Search OpenViking, optionally rerank, return both paths for comparison."""
    raw = backend.search(query, limit=search_limit)
    candidates = []
    for hit in raw.get("resources", []):
        candidates.append({
            "uri": hit.get("uri", ""),
            "score": round(hit.get("score", 0.0), 4),
            "level": hit.get("level", 0),
            "abstract": (hit.get("abstract") or "")[:500],
        })

    result = {
        "query": query,
        "namespace": CORNELL_NAMESPACE,
        "total_candidates": len(candidates),
        "results": candidates[:rerank_top] if not use_reranker else [],
    }

    if not use_reranker:
        result["mode"] = "dense_only"
        return result

    # Rerank
    start = time.monotonic()
    reranked = rerank_candidates(
        query, candidates, model_name=model_name, top_k=rerank_top,
        server_url=server_url,
    )
    elapsed_ms = round((time.monotonic() - start) * 1000, 1)

    # Check if reranker actually fired (has rerank_score) or fell back.
    has_rerank_scores = any("rerank_score" in c for c in reranked)

    result["mode"] = "dense_plus_reranker" if has_rerank_scores else "dense_fallback"
    result["rerank_latency_ms"] = elapsed_ms if has_rerank_scores else None
    result["results"] = reranked
    return result


def cmd_ab_comparison(
    backend: CornellOpenVikingBackend,
    query: str,
    *,
    search_limit: int = DEFAULT_SEARCH_LIMIT,
    rerank_top: int = DEFAULT_RERANK_TOP,
    model_name: str = DEFAULT_RERANKER_MODEL,
    server_url: str = "",
) -> dict[str, Any]:
    """Run dense-only and dense+reranker side by side for comparison."""
    dense_result = search_with_rerank(
        backend, query, search_limit=search_limit, rerank_top=rerank_top,
        use_reranker=False,
    )
    rerank_result = search_with_rerank(
        backend, query, search_limit=search_limit, rerank_top=rerank_top,
        model_name=model_name, use_reranker=True, server_url=server_url,
    )

    # Compare top-k ordering
    dense_uris = [c["uri"] for c in dense_result["results"]]
    rerank_uris = [c["uri"] for c in rerank_result["results"]]
    order_changed = dense_uris != rerank_uris

    return {
        "query": query,
        "search_limit": search_limit,
        "rerank_top": rerank_top,
        "dense_only": {
            "top_uris": dense_uris,
            "results": dense_result["results"],
        },
        "dense_plus_reranker": {
            "mode": rerank_result["mode"],
            "rerank_latency_ms": rerank_result.get("rerank_latency_ms"),
            "top_uris": rerank_uris,
            "results": rerank_result["results"],
        },
        "order_changed": order_changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="reranker",
        description="Cross-encoder reranking for Cornell KB OpenViking retrieval",
    )
    parser.add_argument(
        "command",
        choices=["search", "ab"],
        help="search: retrieve+rerank | ab: compare dense-only vs dense+reranker",
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT,
                        help="Broad candidate set size (default 20)")
    parser.add_argument("--rerank-top", type=int, default=DEFAULT_RERANK_TOP,
                        help="Results to return after reranking (default 5)")
    parser.add_argument("--model", default=DEFAULT_RERANKER_MODEL,
                        help=f"Cross-encoder model (default {DEFAULT_RERANKER_MODEL})")
    parser.add_argument("--no-rerank", action="store_true",
                        help="Skip reranking, return dense-only results")
    parser.add_argument("--server", default=DEFAULT_RERANKER_SERVER,
                        help="Reranker server host:port (e.g. localhost:1940). "
                             "Empty = load model in-process")
    parser.add_argument("--url", default=DEFAULT_OPENVIKING_URL,
                        help="OpenViking server URL")
    parser.add_argument("--timeout", type=float, default=30,
                        help="Request timeout in seconds")
    args = parser.parse_args()

    backend = CornellOpenVikingBackend(base_url=args.url, timeout=args.timeout)

    if args.command == "search":
        result = search_with_rerank(
            backend, args.query,
            search_limit=args.limit,
            rerank_top=args.rerank_top,
            model_name=args.model,
            use_reranker=not args.no_rerank,
            server_url=args.server,
        )
    elif args.command == "ab":
        result = cmd_ab_comparison(
            backend, args.query,
            search_limit=args.limit,
            rerank_top=args.rerank_top,
            model_name=args.model,
            server_url=args.server,
        )
    else:
        parser.error(f"Unknown command: {args.command}")
        return 2

    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())