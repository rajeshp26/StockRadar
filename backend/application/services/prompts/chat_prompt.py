from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, Field

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(...)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1)


def normalize_symbol(symbol: str) -> str:
    from fastapi import HTTPException, status
    s = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid symbol format.",
        )
    return s


def build_chat_system_prompt(symbol: str, company_context: str) -> str:
    return (
        f"You are a digital financial analyst specializing in {symbol}. "
        f"You answer questions about valuation, financial health, and market data "
        f"for {symbol} using the live financial data below.\n\n"
        f"{company_context}\n\n"
        f"Guidelines:\n"
        f"- Be concise and factual. Reference specific numbers from the data.\n"
        f"- If asked about something outside the provided data, say so clearly.\n"
        f"- Do not invent metrics or make up data.\n"
        f"- Use plain English — your audience is a retail investor.\n"
        f"- Keep responses under 3-4 sentences unless the question requires detail."
    )
