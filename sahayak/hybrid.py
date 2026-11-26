"""Hybrid search: BM25 keywords + multilingual embeddings, merged with
Reciprocal Rank Fusion (RRF).

Why both: BM25 nails exact terms ("PMJJBY", "LPG"); embeddings catch
paraphrases and other languages ("बेटी की बचत" -> Sukanya Samriddhi).
RRF merges the two rankings without having to calibrate their scores.

Embeddings use fastembed (ONNX, CPU-only, no PyTorch needed). The default model
is ~220 MB and downloads from Hugging Face the first time.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

import numpy as np

from .models import Scheme
from .search import BM25Index, _doc_text

log = logging.getLogger(__name__)
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class FastEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        from fastembed import TextEmbedding
        self.model = TextEmbedding(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.array(list(self.model.embed(texts)), dtype=np.float32)


def _normalize(m: np.ndarray) -> np.ndarray:
    return m / np.clip(np.linalg.norm(m, axis=-1, keepdims=True), 1e-9, None)


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: score = sum over rankings of 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


class EmbeddingIndex:
    def __init__(self, schemes: dict[str, Scheme], embedder: Embedder):
        self.ids = list(schemes)
        self.embedder = embedder
        self.matrix = _normalize(embedder.encode([_doc_text(schemes[i]) for i in self.ids]))

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        q = _normalize(self.embedder.encode([query]))[0]
        sims = self.matrix @ q
        order = np.argsort(-sims)[:top_k]
        return [(self.ids[i], round(float(sims[i]), 3)) for i in order]


class HybridIndex:
    def __init__(self, schemes: dict[str, Scheme], embedder: Embedder, candidates: int = 10):
        self.bm25 = BM25Index(schemes)
        self.dense = EmbeddingIndex(schemes, embedder)
        self.candidates = candidates

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        kw = [i for i, _ in self.bm25.search(query, self.candidates)]
        dn = [i for i, _ in self.dense.search(query, self.candidates)]
        return [(i, round(s, 4)) for i, s in rrf([kw, dn])[:top_k]]


def build_index(schemes: dict[str, Scheme], mode: str | None = None):
    """mode: 'bm25' | 'dense' | 'hybrid' (default from env SAHAYAK_SEARCH, else 'hybrid').
    Falls back to BM25 if embeddings are unavailable, so the agent always works."""
    mode = (mode or os.environ.get("SAHAYAK_SEARCH", "hybrid")).lower()
    if mode == "bm25":
        return BM25Index(schemes)
    try:
        embedder = FastEmbedder(os.environ.get("SAHAYAK_EMBED_MODEL", DEFAULT_MODEL))
    except Exception as e:  # missing package, no network for first download, etc.
        log.warning("Embeddings unavailable (%s); falling back to BM25 search.", e)
        return BM25Index(schemes)
    return EmbeddingIndex(schemes, embedder) if mode == "dense" else HybridIndex(schemes, embedder)
