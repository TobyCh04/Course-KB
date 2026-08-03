# Expanded Retrieval Benchmark Results

**Run date:** 2026-07-22
**Mode:** offline/local only; `production_services_accessed: false`

## Synthetic regression set

- Corpus: 18 synthetic text sources (`data/test_sources/s01..s18.txt`)
- Queries: 18 hardened paraphrase/formula queries
- Model: `BAAI/bge-small-en-v1.5`

| Strategy | Recall@1 | Recall@5 | MRR |
|---|---:|---:|---:|
| BM25 lexical | 1.000 | 1.000 | 1.000 |
| BGE-small semantic | 1.000 | 1.000 | 1.000 |
| Hybrid RRF | 1.000 | 1.000 | 1.000 |

This is a regression gate, not evidence to promote a larger embedding model: the synthetic domains remain cleanly separated.

## Real-material adversarial control-systems set

- Corpus: 22 verified local sources across notes, source notes, textbooks, lectures, references, homework, and exams
- Queries: 14 with near-duplicate, multi-source, and partial-evidence cases
- Model: `BAAI/bge-small-en-v1.5`
- Source paths: verified

| Strategy | Recall@1 | MRR | Expected-source coverage@5 | Evidence coverage@5 | Distractor top-1 rate |
|---|---:|---:|---:|---:|---:|
| BM25 lexical | 0.857 | 0.929 | 1.000 | 1.000 | 0.000 |
| BGE-small semantic | 0.357 | 0.613 | 0.964 | 0.964 | 0.214 |
| Hybrid RRF | 0.571 | 0.750 | 1.000 | 1.000 | 0.214 |

The adversarial set is the meaningful expanded evaluation. It shows that dense BGE-small and default RRF do not beat the lexical baseline on this corpus, especially for near-duplicates. Do not promote a larger embedding model or change production retrieval defaults from these runs alone; use them as a baseline for the future `bge-base`/`bge-large` A/B test.

## Reproduction

From the project root:

    TORCHINDUCTOR_CACHE_DIR=./.torch-cache python test_runs/synthetic_retrieval_benchmark.py --output test_runs/synthetic_benchmark_results.json
    TORCHINDUCTOR_CACHE_DIR=./.torch-cache python test_runs/control_systems_adversarial_benchmark.py --output test_runs/control_systems_adversarial_results.json
    python -m pytest -q tests/test_synthetic_retrieval_benchmark.py tests/test_control_systems_adversarial_benchmark.py

Both runners are offline and do not ingest benchmark material into OpenViking or Hindsight.
