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
DEFAULT_TOP_K = 5
DEFAULT_MAX_SOURCES = 8
DEFAULT_RERANK_TOP = 20
DEFAULT_RERANK_SCORE_DROP = 0.15
DEFAULT_RERANK_RELATIVE_FLOOR = 0.08
DEFAULT_FUSED_SCORE_DROP = 0.005


def _canonical_uri(uri: str) -> str:
    """Return the directory-level (source-document) URI for deduplication.

    OpenViking may split a single source file into multiple chunk resources
    (e.g. ``foo.json`` → ``foo_1.md``, ``foo_2.md``, …).  Both the lexical
    index and the dense side reference the same *parent directory*, so we
    strip the trailing filename to merge them in RRF.
    """
    if not uri:
        return uri
    relative = uri.removeprefix(f"{CORNELL_NAMESPACE}/")
    if "/" not in relative:
        # A file directly under the namespace is already its own resource.
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
    for item in dense_results:
        can = item.get("canonical_uri") or item.get("uri", "")
        abstract = item.get("abstract", "") or ""
        if can and len(abstract) > len(abstracts.get(can, "")):
            abstracts[can] = abstract
            levels[can] = item.get("level", 0)
    for item in lexical_results:
        can = item.get("canonical_uri") or item.get("uri", "")
        abstract = item.get("abstract", "") or ""
        if can and len(abstract) >= len(abstracts.get(can, "")):
            # Lexical hits often contain the complete source excerpt while
            # dense hits may expose only a short or OCR-damaged abstract.
            # Give the reranker the most informative representation; lexical
            # wins equal-length ties because it is source-text based.
            abstracts[can] = abstract
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


def select_final_sources(
    candidates: list[dict[str, Any]],
    *,
    default_limit: int = DEFAULT_TOP_K,
    max_sources: int = DEFAULT_MAX_SOURCES,
    reranked: bool = True,
    score_drop: float | None = None,
    relative_floor: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a bounded source set using a score-drop cutoff.

    ``default_limit`` is a target budget, not a minimum: candidates below the
    calibrated threshold are excluded even when that returns fewer sources.
    Cross-encoder and RRF scores are on different scales, so the default
    drop is intentionally separate for each. These provisional thresholds are
    returned in the cutoff metadata for later benchmark calibration.
    """
    if default_limit < 1 or max_sources < default_limit:
        raise ValueError("source limits must satisfy 1 <= default_limit <= max_sources")
    if not candidates:
        return [], {"selected_count": 0, "cutoff_reason": "no_candidates"}
    score_key = "rerank_score" if reranked and "rerank_score" in candidates[0] else (
        "fused_score" if "fused_score" in candidates[0] else "score"
    )
    if score_drop is None:
        score_drop = DEFAULT_RERANK_SCORE_DROP if score_key == "rerank_score" else DEFAULT_FUSED_SCORE_DROP
    if relative_floor is None and score_key == "rerank_score":
        relative_floor = DEFAULT_RERANK_RELATIVE_FLOOR
    if relative_floor is not None and not 0 < relative_floor <= 1:
        raise ValueError("relative_floor must be in the range (0, 1]")
    if score_drop < 0:
        raise ValueError("score_drop must be non-negative")

    best_score = float(candidates[0].get(score_key, 0.0))
    threshold = best_score - score_drop
    relative_threshold = None
    if relative_floor is not None and best_score > 0:
        relative_threshold = best_score * relative_floor
        threshold = max(threshold, relative_threshold)
    selected: list[dict[str, Any]] = []
    cutoff_reason = "candidate_limit"
    for candidate in candidates:
        if len(selected) >= max_sources:
            cutoff_reason = "max_sources"
            break
        score = float(candidate.get(score_key, 0.0))
        if selected and score < threshold:
            cutoff_reason = "score_drop"
            break
        selected.append(candidate)

    return selected, {
        "selected_count": len(selected),
        "score_key": score_key,
        "best_score": best_score,
        "score_threshold": threshold,
        "score_drop": score_drop,
        "relative_floor": relative_floor,
        "relative_threshold": relative_threshold,
        "cutoff_reason": cutoff_reason,
        "default_limit": default_limit,
        "max_sources": max_sources,
    }


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
    rerank_top: int = DEFAULT_RERANK_TOP,
    rerank_server_url: str = "",
    max_sources: int = DEFAULT_MAX_SOURCES,
    rerank_score_drop: float | None = None,
) -> dict[str, Any]:
    """Search OpenViking + BM25, fuse with RRF, then rerank by default.

    Set ``rerank_top=0`` only for an explicit diagnostic bypass.

    Args:
        backend: OpenViking backend (dense retrieval).
        query: User query.
        index_path: Path to the BM25 lexical index JSON.
        search_limit: Number of dense candidates to retrieve (pre-dedup).
        lexical_limit: Number of lexical candidates to retrieve.
        top_k: Default number of final source documents; dynamic selection may
            expand this up to ``max_sources``.
        k: RRF smoothing constant.
        dense_weight: Weight for dense ranks in RRF.
        lexical_weight: Weight for lexical ranks in RRF.
        rerank_top: Number of fused candidates to rerank. The default reranks
            the full candidate pool; set to 0 only for diagnostics.
        rerank_server_url: Optional persistent reranker server (host:port).
        max_sources: Hard maximum for final source documents.

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
        rerank_candidates = fused[:min(rerank_top, len(fused))]
        reranked = reranker_mod.rerank_candidates(
            query,
            rerank_candidates,
            top_k=len(rerank_candidates),
            server_url=rerank_server_url,
        )
        rerank_ms = round((time.monotonic() - rerank_start) * 1000, 2)
        has_rerank_scores = any("rerank_score" in c for c in reranked)
        result["mode"] = "dense_lexical_reranker" if has_rerank_scores else "dense_lexical_fallback"
        result["rerank_latency_ms"] = rerank_ms if has_rerank_scores else None
        result["rerank_candidates"] = len(reranked)
        selected, cutoff = select_final_sources(
            reranked,
            default_limit=top_k,
            max_sources=max_sources,
            reranked=has_rerank_scores,
            score_drop=rerank_score_drop,
        )
        result["results"] = selected
        result["source_cutoff"] = cutoff
    else:
        result["mode"] = "dense_plus_lexical"
        selected, cutoff = select_final_sources(
            fused,
            default_limit=top_k,
            max_sources=max_sources,
            reranked=False,
        )
        result["results"] = selected
        result["source_cutoff"] = cutoff

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
        help="Default final source count (default 5)",
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
        "--rerank-top", type=int, default=DEFAULT_RERANK_TOP,
        help="Fused candidates to rerank; 0 explicitly disables reranking",
    )
    search_parser.add_argument(
        "--rerank-server", default="",
        help="Persistent reranker server host:port (e.g. localhost:1940)",
    )
    search_parser.add_argument(
        "--max-sources", type=int, default=DEFAULT_MAX_SOURCES,
        help="Hard maximum final source documents (default 8)",
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
            max_sources=args.max_sources,
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
