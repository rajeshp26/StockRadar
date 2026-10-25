"""Memory gateway — Pattern 8, Memory Management (Gulli Ch 8; Lanham Ch 6).

Tiers: session/state with scope prefixes (session: < app: < user:, temp:
dies with the run), semantic long-term memory (vector-ish store over a
deterministic hashing embedder), episodic log, and a versioned procedural
store governed like code. State is written through events/deltas, never by
direct mutation of a shared dict."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Optional


def _embed(text: str, dims: int = 64) -> list[float]:
    """Deterministic hashing embedder: a stand-in for a real embedding
    model, good enough to exercise retrieval semantics offline."""
    vec = [0.0] * dims
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class StateDelta:
    key: str
    value: Any


@dataclass
class SessionState:
    """Scope-prefixed state. Prefixes: temp: (run), session: (session),
    user: (per user, cross-session), app: (global)."""
    _store: dict[str, Any] = field(default_factory=dict)
    events: list[StateDelta] = field(default_factory=list)

    def apply(self, delta: StateDelta) -> None:
        self.events.append(delta)
        self._store[delta.key] = delta.value

    def set(self, key: str, value: Any) -> None:
        self.apply(StateDelta(key, value))

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def scoped_view(self, *prefixes: str) -> dict[str, Any]:
        # Segment-boundary matching (round-3): a raw startswith made
        # scoped_view("user:alice") also return "user:alice2:secret" —
        # a silent isolation leak in the component whose whole job is
        # scoped isolation. A prefix matches a key equal to it, or keys
        # under it at a ':' boundary; an empty prefix matches nothing
        # (it used to match EVERYTHING).
        def matches(k: str, p: str) -> bool:
            if not p:
                return False
            return k == p or k.startswith(p if p.endswith(":") else p + ":")
        return {k: v for k, v in self._store.items()
                if any(matches(k, p) for p in prefixes)}


@dataclass
class SemanticMemory:
    """Long-term semantic memory with top-k + distance-threshold retrieval
    (Gulli Ch 8 Vertex Memory Bank tuning knobs)."""
    items: list[tuple[str, list[float], dict]] = field(default_factory=list)

    def add(self, text: str, metadata: Optional[dict] = None) -> None:
        self.items.append((text, _embed(text), metadata or {}))

    def search(self, query: str, *, top_k: int = 5,
               threshold: float = 0.1) -> list[tuple[str, float, dict]]:
        if top_k <= 0:
            # Negative top_k used to leak Python slice semantics
            # (all-but-the-last-N) across every retrieval surface
            # (round-3). Zero/negative means "no results", uniformly.
            return []
        q = _embed(query)
        scored = [(text, cosine(q, vec), meta) for text, vec, meta in self.items]
        scored = [s for s in scored if s[1] >= threshold]
        return sorted(scored, key=lambda s: -s[1])[:top_k]


@dataclass
class EpisodicMemory:
    """Append-only log of (situation -> outcome) episodes."""
    episodes: list[dict] = field(default_factory=list)

    def record(self, situation: str, action: str, outcome: str) -> None:
        self.episodes.append(
            {"situation": situation, "action": action, "outcome": outcome})

    def recall_similar(self, situation: str) -> list[dict]:
        # Round-3: this used to take a `memory: SemanticMemory` parameter
        # it never read, inviting callers to believe the shared store was
        # being searched. It searches THIS log's episodes; the dead
        # parameter is gone rather than decorative.
        idx = SemanticMemory()
        for ep in self.episodes:
            idx.add(ep["situation"], ep)
        return [meta for _, _, meta in idx.search(situation, top_k=3)]


@dataclass
class ProceduralMemory:
    """Versioned how-to entries. Updates create a new version; rollback is
    a first-class operation (self-modifying memory governed like code).

    Round-3 hardening: version numbers are MONOTONIC per name — the old
    len()-based numbering reused numbers after a rollback (v2, rollback,
    new write = "v2" again), and the store dict was publicly mutable, so
    get() could be changed without set() ever being called. History is
    now private; read it via history()."""
    _history: dict[str, list[str]] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def set(self, name: str, instructions: str) -> int:
        self._history.setdefault(name, []).append(instructions)
        self._counters[name] = self._counters.get(name, 0) + 1
        return self._counters[name]

    def get(self, name: str) -> Optional[str]:
        vs = self._history.get(name)
        return vs[-1] if vs else None

    def history(self, name: str) -> list[str]:
        """A copy of the version stack for `name` (oldest first)."""
        return list(self._history.get(name, []))

    def rollback(self, name: str) -> Optional[str]:
        vs = self._history.get(name)
        if vs and len(vs) > 1:
            vs.pop()
        return self.get(name)


@dataclass
class MemoryGateway:
    state: SessionState = field(default_factory=SessionState)
    semantic: SemanticMemory = field(default_factory=SemanticMemory)
    episodic: EpisodicMemory = field(default_factory=EpisodicMemory)
    procedural: ProceduralMemory = field(default_factory=ProceduralMemory)

    def remember(self, text: str, metadata: Optional[dict] = None) -> None:
        self.semantic.add(text, metadata)

    def recall(self, query: str, *, top_k: int = 5) -> list[tuple[str, float, dict]]:
        return self.semantic.search(query, top_k=top_k)
