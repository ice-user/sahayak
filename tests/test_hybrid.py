import hashlib

import numpy as np

from sahayak.hybrid import EmbeddingIndex, HybridIndex, build_index, rrf
from sahayak.models import load_schemes
from sahayak.search import BM25Index, tokenize

SCHEMES = load_schemes()


class HashEmbedder:
    """Deterministic stand-in for a real model: hashed bag of words. Tests the plumbing, not quality."""
    dim = 256

    def encode(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for tok in tokenize(text):
                out[row, int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        return out


def test_rrf_rewards_agreement():
    fused = dict(rrf([["a", "b", "c"], ["b", "a", "d"]]))
    assert fused["a"] == fused["b"] > fused["c"] > 0
    assert fused["c"] == fused["d"]


def test_rrf_single_list_keeps_order():
    assert [i for i, _ in rrf([["x", "y", "z"]])] == ["x", "y", "z"]


def test_embedding_index_finds_scheme():
    idx = EmbeddingIndex(SCHEMES, HashEmbedder())
    assert idx.search("widow pension vidhwa", 3)[0][0] == "ignwps"


def test_hybrid_returns_top_k_unique():
    idx = HybridIndex(SCHEMES, HashEmbedder())
    hits = idx.search("insurance", 4)
    ids = [i for i, _ in hits]
    assert len(ids) == len(set(ids)) <= 4
    assert {"pmjjby", "pmsby"} & set(ids)


def test_build_index_bm25_mode():
    assert isinstance(build_index(SCHEMES, "bm25"), BM25Index)


def test_build_index_falls_back_without_embeddings(monkeypatch):
    import sahayak.hybrid as h

    def boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(h, "FastEmbedder", boom)
    assert isinstance(build_index(SCHEMES, "hybrid"), BM25Index)
