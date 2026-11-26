"""Keyword search (BM25) over schemes. No external dependencies.

This is the baseline retriever. Step 2 of the roadmap adds embeddings and
hybrid search; keep this one so the eval can compare them.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .models import Scheme

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _doc_text(s: Scheme) -> str:
    return " ".join([s.name, s.summary, s.benefits, s.category, " ".join(s.tags), " ".join(s.aliases)])


class BM25Index:
    def __init__(self, schemes: dict[str, Scheme], k1: float = 1.5, b: float = 0.75):
        self.ids = list(schemes)
        self.docs = [tokenize(_doc_text(schemes[i])) for i in self.ids]
        self.tf = [Counter(d) for d in self.docs]
        self.avgdl = sum(len(d) for d in self.docs) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        q = tokenize(query)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            score = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                score += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if score > 0:
                scores.append((self.ids[i], round(score, 3)))
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]
