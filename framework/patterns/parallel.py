"""Pattern 3 — Parallelization (Gulli Ch 3).

Independent branches run concurrently into separate state keys; a
synthesiser with no tools merges, grounded only in branch outputs."""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from llm import LLM


async def run_parallel(
    branches: dict[str, Callable[[], Awaitable[str]]]
) -> dict[str, str]:
    keys = list(branches)
    values = await asyncio.gather(*(branches[k]() for k in keys))
    return dict(zip(keys, values))


def synthesise(llm: LLM, topic: str, branch_outputs: dict[str, str]) -> str:
    briefs = "\n\n".join(f"[{k}]\n{v}" for k, v in branch_outputs.items())
    return llm.complete(
        f"Write one report on '{topic}' using ONLY the briefs below. "
        f"Attribute each claim to its brief.\n\n{briefs}"
    )
