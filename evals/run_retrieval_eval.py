"""Compare BM25 vs embeddings vs hybrid on evals/retrieval_cases.json.

    python -m evals.run_retrieval_eval

Prints hit@1, hit@3 and MRR overall and for non-English queries.
Downloads the embedding model (~220 MB) on first run.
"""
from __future__ import annotations

import json
from pathlib import Path

from sahayak.hybrid import DEFAULT_MODEL, EmbeddingIndex, FastEmbedder, HybridIndex
from sahayak.models import load_schemes
from sahayak.search import BM25Index

CASES = json.loads((Path(__file__).parent / "retrieval_cases.json").read_text(encoding="utf-8"))


def evaluate(index, cases) -> dict:
    h1 = h3 = mrr = 0.0
    for c in cases:
        ids = [i for i, _ in index.search(c["q"], 10)]
        rank = ids.index(c["expect"]) + 1 if c["expect"] in ids else None
        h1 += rank == 1
        h3 += bool(rank and rank <= 3)
        mrr += 1 / rank if rank else 0
    n = len(cases)
    return {"hit@1": round(h1 / n, 2), "hit@3": round(h3 / n, 2), "mrr": round(mrr / n, 2), "n": n}


def main():
    schemes = load_schemes()
    embedder = FastEmbedder(DEFAULT_MODEL)
    indexes = {"bm25": BM25Index(schemes), "dense": EmbeddingIndex(schemes, embedder),
               "hybrid": HybridIndex(schemes, embedder)}
    subsets = {"all": CASES, "non-english": [c for c in CASES if c.get("lang", "en") != "en"]}
    print(f"{'index':<8} {'subset':<12} hit@1  hit@3  mrr   n")
    for name, idx in indexes.items():
        for sub, cases in subsets.items():
            r = evaluate(idx, cases)
            print(f"{name:<8} {sub:<12} {r['hit@1']:<6} {r['hit@3']:<6} {r['mrr']:<5} {r['n']}")


if __name__ == "__main__":
    main()
