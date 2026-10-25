"""Retrieval — Pattern 14, Knowledge Retrieval / RAG (Gulli Ch 14;
Lanham Ch 6).

Chunking with overlap, a keyword (TF-IDF) index, a vector index, hybrid
fusion via Reciprocal Rank Fusion, and the grounded-answer contract:
answer only from retrieved passages, cite, or say you don't know."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .memory_gateway import _embed, cosine


def chunk_text(text: str, *, size: int = 500, overlap: int = 50) -> list[str]:
    if size < 1:
        raise ValueError("chunk size must be >= 1")
    if overlap < 0 or overlap >= size:
        # The step is size - overlap; a non-positive step never advances
        # the cursor — the old code infinite-looped with growing memory
        # on size=0, overlap>=size, or negative size (round-3, R3G-1).
        raise ValueError("overlap must satisfy 0 <= overlap < size")
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        if i + size >= len(text):
            break
        i += size - overlap
    return chunks


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class Document:
    id: str
    text: str
    source: str = ""


@dataclass
class KeywordIndex:
    docs: list[Document] = field(default_factory=list)
    _idf: dict[str, float] = field(default_factory=dict)

    def add(self, doc: Document) -> None:
        self.docs.append(doc)
        self._idf = {}

    def _idf_of(self, term: str) -> float:
        if not self._idf:
            n = len(self.docs)
            df: Counter = Counter()
            for d in self.docs:
                for t in set(_tokens(d.text)):
                    df[t] += 1
            self._idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        return self._idf.get(term, math.log(len(self.docs) + 1) + 1)

    def search(self, query: str, top: int = 5) -> list[Document]:
        if top <= 0:
            return []  # negative top used to slice-leak (round-3)
        q = Counter(_tokens(query))
        scored = []
        seen: set[str] = set()
        for d in self.docs:
            if d.id in seen:
                continue  # same id added twice: first copy wins
            dt = Counter(_tokens(d.text))
            score = sum(q[t] * dt.get(t, 0) * self._idf_of(t) for t in q)
            if score > 0:
                seen.add(d.id)
                scored.append((score, d))
        return [d for _, d in sorted(scored, key=lambda s: -s[0])[:top]]


@dataclass
class VectorIndex:
    docs: list[Document] = field(default_factory=list)

    def add(self, doc: Document) -> None:
        self.docs.append(doc)

    def search(self, query: str, top: int = 5, threshold: float = 0.05) -> list[Document]:
        if top <= 0:
            return []  # negative top used to slice-leak (round-3)
        q = _embed(query)
        scored = [(cosine(q, _embed(d.text)), d) for d in self.docs]
        scored = [s for s in scored if s[0] >= threshold]
        return [d for _, d in sorted(scored, key=lambda s: -s[0])[:top]]


def hybrid_search(query: str, kw: KeywordIndex, vec: VectorIndex,
                  *, k: int = 60, top: int = 5) -> list[Document]:
    """Reciprocal Rank Fusion: score = sum(1 / (k + rank))."""
    if k < 0:
        # k=-1 divided by zero at rank 1; other negatives invert the
        # fusion scores (round-3).
        raise ValueError("RRF constant k must be >= 0")
    if top <= 0:
        return []
    scores: dict[str, float] = {}
    by_id: dict[str, Document] = {}
    for rank, d in enumerate(kw.search(query, top=top * 2), start=1):
        scores[d.id] = scores.get(d.id, 0.0) + 1.0 / (k + rank)
        by_id.setdefault(d.id, d)
    for rank, d in enumerate(vec.search(query, top=top * 2), start=1):
        scores[d.id] = scores.get(d.id, 0.0) + 1.0 / (k + rank)
        # First-seen document wins an id collision (round-3): when the
        # two indexes hold different documents under one id, the vector
        # copy used to silently replace the keyword copy.
        by_id.setdefault(d.id, d)
    ranked = sorted(scores, key=lambda i: -scores[i])[:top]
    return [by_id[i] for i in ranked]


def mmr_rerank(query: str, docs: list[Document], *, top: int = 5,
               lambda_: float = 0.5) -> list[Document]:
    """Maximal Marginal Relevance (Lanham Ch 6 failure-mode fix): trade
    relevance against redundancy so near-duplicates don't crowd top-K."""
    if not docs:
        return []
    q = _embed(query)
    remaining = [(cosine(q, _embed(d.text)), d) for d in docs]
    selected: list[Document] = []
    selected_vecs: list[list[float]] = []
    while remaining and len(selected) < top:
        best_i, best_score = 0, float("-inf")
        for i, (rel, d) in enumerate(remaining):
            dv = _embed(d.text)
            redundancy = max((cosine(dv, sv) for sv in selected_vecs), default=0.0)
            score = lambda_ * rel - (1 - lambda_) * redundancy
            if score > best_score:
                best_i, best_score = i, score
        _, doc = remaining.pop(best_i)
        selected.append(doc)
        selected_vecs.append(_embed(doc.text))
    return selected


DONT_KNOW = "I don't know based on the available documents."


def grounded_answer(llm_complete, question: str, passages: list[Document],
                    *, mode: str = "strong") -> str:
    """The grounding contract, with Lanham Ch 6's two modes.
    strong: every claim traceable to a passage; abstain when unsupported.
    weak:   outside information may be added (internal research use).
    No passages -> abstain without calling the model, in both modes."""
    if mode not in ("strong", "weak"):
        # Validate before the no-passages return (round-3 minor): a
        # bogus mode used to be silently masked by empty results.
        raise ValueError("mode must be 'strong' or 'weak'")
    if not passages:
        return DONT_KNOW
    context = "\n\n".join(f"[Reference {i + 1}: {d.source or d.id}] {d.text}"
                          for i, d in enumerate(passages))
    if mode == "strong":
        instruction = (
            "Answer using ONLY the passages below. Quote the relevant "
            "passage first, then give your interpretation, citing like "
            f"[Reference 1]. If the passages do not support an answer, "
            f"reply exactly: '{DONT_KNOW}'")
    elif mode == "weak":
        instruction = (
            "Answer primarily from the passages below, citing like "
            "[Reference 1]; you may add clearly-marked outside knowledge "
            "where the passages are silent.")
    else:
        raise ValueError("mode must be 'strong' or 'weak'")
    return llm_complete(
        f"{instruction}\n\nPassages:\n{context}\n\nQuestion: {question}")
