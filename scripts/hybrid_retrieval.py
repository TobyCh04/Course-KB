"""Dense + lexical hybrid retrieval for Cornell KB.

Combines OpenViking dense results with a local BM25 lexical index using
Reciprocal Rank Fusion (RRF), then optionally reranks with a cross-encoder.

Usage:
    python scripts/hybrid_retrieval.py search "kanban" --index-path data/lexical_index.json
    python scripts/hybrid_retrieval.py ab "DG/(1+DGH)" --index-path data/lexical_index.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    from .lexical_index import DEFAULT_ROOT, LexicalIndex, build_lexical_index, load_index, save_index
    from .openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE
    from . import reranker as reranker_mod
except ImportError:  # pragma: no cover - exercised by direct CLI use
    from lexical_index import DEFAULT_ROOT, LexicalIndex, build_lexical_index, load_index, save_index
    from openviking_backend import CornellOpenVikingBackend, CORNELL_NAMESPACE
    import reranker as reranker_mod
DEFAULT_OPENVIKING_URL = "http://127.0.0.1:1934"
DEFAULT_INDEX_PATH = Path("data/lexical_index.json")
DEFAULT_RRF_K = 60
DEFAULT_DENSE_WEIGHT = 1.0
DEFAULT_LEXICAL_WEIGHT = 1.0
DEFAULT_SEARCH_LIMIT = 20
DEFAULT_LEXICAL_LIMIT = 20
DEFAULT_TOP_K = 10
DEFAULT_RERANK_TOP = 0


def _canonical_uri(uri: str) -> str:
    """Return the directory-level (source-document) URI for deduplication.

    OpenViking may split a single source file into multiple chunk resources
    (e.g. ``foo.json`` → ``foo_1.md``, ``foo_2.md``, …).  Both the lexical
    index and the dense side reference the same *parent directory*, so we
    strip the trailing filename to merge them in RRF.
    """
    if not uri:
        return uri
    # Keep everything up to the last "/" — the resource container directory.
    return uri.rsplit("/", 1)[0]


def _normalize_dense_result(hit: dict[str, Any]) -> dict[str, Any]:
    """Convert an OpenViking search hit into the canonical candidate shape."""
    return {
        "uri": hit.get("uri", ""),
        "canonical_uri": _canonical_uri(hit.get("uri", "")),
        "score": round(hit.get("score", 0.0), 4),
        "level": hit.get("level", 0),
        "abstract": (hit.get("abstract") or "")[:500],
        "source": "dense",
    }


def _normalize_lexical_result(hit: dict[str, Any]) -> dict[str, Any]:
    """Convert a BM25 hit into the canonical candidate shape."""
    return {
        "uri": hit.get("uri", ""),
        "canonical_uri": _canonical_uri(hit.get("uri", "")),
        "score": round(hit.get("score", 0.0), 4),
        "level": 0,
        "abstract": hit.get("abstract", "")[:500],
        "source": "lexical",
    }


def reciprocal_rank_fusion(
    dense_results: list[dict[str, Any]],
    lexical_results: list[dict[str, Any]],
    *,
    k: int = DEFAULT_RRF_K,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
) -> list[dict[str, Any]]:
    """Merge dense and lexical rankings using RRF.

    score(uri) = weight_dense * sum(1/(k + rank_dense)) +
                 weight_lexical * sum(1/(k + rank_lexical))

    Results are returned sorted by fused score descending. Each result includes
    the list of source ranks that contributed to the score.

    Deduplication uses ``canonical_uri`` (directory-level) so that OpenViking
    chunk resources and lexical index entries for the same source document are
    merged correctly.
    """
    if k <= 0:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = {}
    provenance: dict[str, list[dict[str, Any]]] = {}
    best_uri: dict[str, str] = {}

    def _process(results: list[dict[str, Any]], weight: float, source: str) -> None:
        for rank, item in enumerate(results, start=1):
            can = item.get("canonical_uri") or item.get("uri", "")
            if not can:
                continue
            scores[can] = scores.get(can, 0.0) + weight * (1.0 / (k + rank))
            provenance.setdefault(can, []).append({
                "source": source,
                "rank": rank,
                "score": item.get("score"),
            })
            if can not in best_uri:
                best_uri[can] = item.get("uri", can)

    _process(dense_results, dense_weight, "dense")
    _process(lexical_results, lexical_weight, "lexical")

    # Build a lookup for the best abstract per canonical URI.
    abstracts: dict[str, str] = {}
    levels: dict[str, int] = {}
    for item in dense_results + lexical_results:
        can = item.get("canonical_uri") or item.get("uri", "")
        if can and can not in abstracts:
            abstracts[can] = item.get("abstract", "")
            levels[can] = item.get("level", 0)

    merged = []
    for can, fused_score in scores.items():
        merged.append({
            "uri": best_uri.get(can, can),
            "canonical_uri": can,
            "fused_score": round(fused_score, 4),
            "abstract": abstracts.get(can, ""),
            "level": levels.get(can, 0),
            "provenance": provenance.get(can, []),
        })

    merged.sort(key=lambda x: x["fused_score"], reverse=True)
    return merged


def lexical_search(
    query: str,
    index_path: Path,
    *,
    limit: int = DEFAULT_LEXICAL_LIMIT,
) -> list[dict[str, Any]]:
    """Search the local BM25 index and return normalized candidates."""
    index = load_index(index_path)
    return [_normalize_lexical_result(r) for r in index.search(query, top_k=limit)]


def ensure_lexical_index(
    index_path: Path,
    root: Path,
    *,
    force_rebuild: bool = False,
) -> LexicalIndex:
    """Return a loaded BM25 index, building it first if it is missing or stale."""
    index_path = Path(index_path).expanduser()
    if not force_rebuild and index_path.is_file():
        return load_index(index_path)
    index = build_lexical_index(root)
    save_index(index, index_path)
    return index


def _dedupe_by_canonical_uri(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the highest-scoring candidate per canonical URI.

    OpenViking splits large source files into multiple chunk resources, each
    with its own score and rank.  Without deduplication a document with 5
    chunks would accumulate 5 RRF contributions and unfairly outrank a
    single-chunk document at the same semantic relevance.

    The input is assumed to be sorted by descending score (OpenViking returns
    results pre-ranked).  We keep the first occurrence of each canonical URI.
    """
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in results:
        can = item.get("canonical_uri") or item.get("uri", "")
        if not can or can in seen:
            continue
        seen.add(can)
        deduped.append(item)
    return deduped


def hybrid_search(
    backend: CornellOpenVikingBackend,
    query: str,
    *,
    index_path: Path = DEFAULT_INDEX_PATH,
    search_limit: int = DEFAULT_SEARCH_LIMIT,
    lexical_limit: int = DEFAULT_LEXICAL_LIMIT,
    top_k: int = DEFAULT_TOP_K,
    k: int = DEFAULT_RRF_K,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
    rerank_top: int = 0,
    rerank_server_url: str = "",
) -> dict[str, Any]:
    """Search OpenViking + BM25, fuse with RRF, optionally rerank.

    Args:
        backend: OpenViking backend (dense retrieval).
        query: User query.
        index_path: Path to the BM25 lexical index JSON.
        search_limit: Number of dense candidates to retrieve (pre-dedup).
        lexical_limit: Number of lexical candidates to retrieve.
        top_k: Number of results to return after fusion (and reranking).
        k: RRF smoothing constant.
        dense_weight: Weight for dense ranks in RRF.
        lexical_weight: Weight for lexical ranks in RRF.
        rerank_top: If > 0, rerank the top N fused results with the cross-encoder.
        rerank_server_url: Optional persistent reranker server (host:port).

    Returns:
        Result dict with query, mode, candidate counts, and results.
    """
    # Dense retrieval
    dense_raw = backend.search(query, limit=search_limit)
    _dense_all = [_normalize_dense_result(h) for h in dense_raw.get("resources", [])]
    # Deduplicate: keep only the best-scoring chunk per source document so
    # that multi-chunk documents don't inflate RRF scores.
    dense_results = _dedupe_by_canonical_uri(_dense_all)

    # Lexical retrieval
    lexical_results = lexical_search(query, index_path, limit=lexical_limit)

    start = time.monotonic()
    fused = reciprocal_rank_fusion(
        dense_results,
        lexical_results,
        k=k,
        dense_weight=dense_weight,
        lexical_weight=lexical_weight,
    )
    fusion_ms = round((time.monotonic() - start) * 1000, 2)

    result = {
        "query": query,
        "namespace": CORNELL_NAMESPACE,
        "mode": "dense_plus_lexical",
        "dense_candidates": len(dense_results),
        "lexical_candidates": len(lexical_results),
        "fusion_latency_ms": fusion_ms,
        "results": fused[:top_k],
    }

    if rerank_top > 0 and fused:
        rerank_start = time.monotonic()
        reranked = reranker_mod.rerank_candidates(
            query,
            fused[:rerank_top],
            top_k=rerank_top,
            server_url=rerank_server_url,
        )
        rerank_ms = round((time.monotonic() - rerank_start) * 1000, 2)
        has_rerank_scores = any("rerank_score" in c for c in reranked)
        result["mode"] = "dense_lexical_reranker" if has_rerank_scores else "dense_lexical_fallback"
        result["rerank_latency_ms"] = rerank_ms if has_rerank_scores else None
        result["results"] = reranked
    else:
        result["mode"] = "dense_plus_lexical"

    return result


def hybrid_ab_comparison(
    backend: CornellOpenVikingBackend,
    query: str,
    *,
    index_path: Path = DEFAULT_INDEX_PATH,
    search_limit: int = DEFAULT_SEARCH_LIMIT,
    lexical_limit: int = DEFAULT_LEXICAL_LIMIT,
    top_k: int = DEFAULT_TOP_K,
    k: int = DEFAULT_RRF_K,
    dense_weight: float = DEFAULT_DENSE_WEIGHT,
    lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
) -> dict[str, Any]:
    """Compare dense-only, lexical-only, and fused retrieval on the same query."""
    dense_raw = backend.search(query, limit=search_limit)
    _dense_all = [_normalize_dense_result(h) for h in dense_raw.get("resources", [])]
    dense_results = _dedupe_by_canonical_uri(_dense_all)
    lexical_results = lexical_search(query, index_path, limit=lexical_limit)
    fused = reciprocal_rank_fusion(
        dense_results, lexical_results, k=k,
        dense_weight=dense_weight, lexical_weight=lexical_weight,
    )

    return {
        "query": query,
        "dense_top_uris": [r["uri"] for r in dense_results[:top_k]],
        "lexical_top_uris": [r["uri"] for r in lexical_results[:top_k]],
        "fused_top_uris": [r["uri"] for r in fused[:top_k]],
        "dense_results": dense_results[:top_k],
        "lexical_results": lexical_results[:top_k],
        "fused_results": fused[:top_k],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="hybrid_retrieval",
        description="Dense + BM25 lexical hybrid retrieval for Cornell KB",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Run hybrid retrieval")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--index-path", default=str(DEFAULT_INDEX_PATH),
        help="Path to the BM25 index JSON",
    )
    search_parser.add_argument(
        "--url", default=DEFAULT_OPENVIKING_URL,
        help="OpenViking server URL",
    )
    search_parser.add_argument(
        "--search-limit", type=int, default=DEFAULT_SEARCH_LIMIT,
        help="Dense candidate count",
    )
    search_parser.add_argument(
        "--lexical-limit", type=int, default=DEFAULT_LEXICAL_LIMIT,
        help="Lexical candidate count",
    )
    search_parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K,
        help="Results to return after fusion",
    )
    search_parser.add_argument(
        "--rrf-k", type=int, default=DEFAULT_RRF_K,
        help="RRF smoothing constant",
    )
    search_parser.add_argument(
        "--dense-weight", type=float, default=DEFAULT_DENSE_WEIGHT,
        help="Weight for dense ranks in RRF",
    )
    search_parser.add_argument(
        "--lexical-weight", type=float, default=DEFAULT_LEXICAL_WEIGHT,
        help="Weight for lexical ranks in RRF",
    )
    search_parser.add_argument(
        "--rerank-top", type=int, default=0,
        help="If > 0, rerank the top N fused results with the cross-encoder",
    )
    search_parser.add_argument(
        "--rerank-server", default="",
        help="Persistent reranker server host:port (e.g. localhost:1940)",
    )
    search_parser.add_argument(
        "--build", action="store_true",
        help="Rebuild the lexical index before searching",
    )
    search_parser.add_argument(
        "--root", default=str(DEFAULT_ROOT),
        help="Cornell KB root directory (for --build)",
    )

    ab_parser = subparsers.add_parser("ab", help="Compare dense vs lexical vs fused")
    ab_parser.add_argument("query", help="Search query")
    ab_parser.add_argument(
        "--index-path", default=str(DEFAULT_INDEX_PATH),
        help="Path to the BM25 index JSON",
    )
    ab_parser.add_argument(
        "--url", default=DEFAULT_OPENVIKING_URL,
        help="OpenViking server URL",
    )
    ab_parser.add_argument(
        "--search-limit", type=int, default=DEFAULT_SEARCH_LIMIT,
        help="Dense candidate count",
    )
    ab_parser.add_argument(
        "--lexical-limit", type=int, default=DEFAULT_LEXICAL_LIMIT,
        help="Lexical candidate count",
    )
    ab_parser.add_argument(
        "--top-k", type=int, default=DEFAULT_TOP_K,
        help="Results to compare",
    )

    args = parser.parse_args()

    backend = CornellOpenVikingBackend(base_url=args.url, timeout=30)
    index_path = Path(args.index_path)

    if args.command == "search":
        if args.build:
            ensure_lexical_index(index_path, Path(args.root), force_rebuild=True)
        result = hybrid_search(
            backend, args.query,
            index_path=index_path,
            search_limit=args.search_limit,
            lexical_limit=args.lexical_limit,
            top_k=args.top_k,
            k=args.rrf_k,
            dense_weight=args.dense_weight,
            lexical_weight=args.lexical_weight,
            rerank_top=args.rerank_top,
            rerank_server_url=args.rerank_server,
        )
    elif args.command == "ab":
        result = hybrid_ab_comparison(
            backend, args.query,
            index_path=index_path,
            search_limit=args.search_limit,
            lexical_limit=args.lexical_limit,
            top_k=args.top_k,
        )
    else:
        parser.error(f"Unknown command: {args.command}")
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
