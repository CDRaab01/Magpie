"""Ask-your-ledger chat (ROADMAP #21) — the largest AI surface, so the guardrail is the point.

The Plate `coach_chat` shape over money: a server-side system prompt pins the model to *descriptive*
finance over a **trusted aggregate context** (category/merchant/month rollups — never a raw row,
never an email), read-only, no tool access. Investment/tax/legal advice is out of scope by
construction (CLAUDE.md §6). Every user turn is validated (injection can hide in history, not just
the latest turn), the context is a system message the user's turns cannot overwrite, and a failed
or absent model degrades to a plain "can't answer right now" rather than raising into the caller.
"""

import json

from app.services.ai.llm_client import LlmClient

MAX_MESSAGE_CHARS = 1000
MAX_HISTORY_TURNS = 8

_SYSTEM = (
    "You are Magpie, a household-finance assistant. Answer questions about this household's money "
    "using ONLY the figures in the AGGREGATES section below. Rules, without exception:\n"
    "- Use only the numbers given; never invent a figure. If the aggregates don't cover the "
    "question, say so plainly.\n"
    "- Be grounded: report what the numbers say. You MAY give practical budget coaching about "
    "this household's own spending measured against its own budgets and savings goal in the "
    "budgets_this_month / savings_goal sections — which categories are over pace and what would "
    "bring them back on budget. Any change you suggest is only a suggestion the owner confirms "
    "in the app's Budgets screen; you cannot change budgets or goals yourself, so when asked to "
    "make a change, describe it and point at the Budgets screen. Give no investment, tax, or "
    "legal advice, and never recommend financial products.\n"
    "- You have no access to individual transactions, emails, account numbers, or any tool — only "
    "these aggregates. Do not claim otherwise.\n"
    "- Keep answers short and specific, in plain language with dollar figures."
)

_FALLBACK = "I can't answer that right now — the local model didn't respond. Try again in a moment."


def validate_user_message(text: str) -> str | None:
    """Return an error string if a user turn is unusable, else None. Length-capped so a pasted
    wall of text can't blow the local context window; empties rejected."""
    if not text or not text.strip():
        return "Ask a question about your spending."
    if len(text) > MAX_MESSAGE_CHARS:
        return f"That's too long — keep it under {MAX_MESSAGE_CHARS} characters."
    return None


def build_messages(context: dict, history: list[dict], question: str) -> list[dict]:
    """The message list handed to the model: the guardrail system prompt with the aggregates
    embedded (a system role the user cannot override), then the trimmed prior turns, then the
    latest question. History is capped so a long chat can't grow the request unbounded."""
    system = f"{_SYSTEM}\n\nAGGREGATES (JSON):\n{json.dumps(context, indent=1, default=str)}"
    trimmed = [m for m in history if m.get("role") in ("user", "assistant")][-MAX_HISTORY_TURNS:]
    return [{"role": "system", "content": system}, *trimmed, {"role": "user", "content": question}]


async def answer(client: LlmClient, context: dict, history: list[dict], question: str) -> str:
    """The model's answer, or a plain fallback on any failure (§6: prose is best-effort; a hiccup
    never surfaces a stack trace to the user)."""
    try:
        reply = (await client.chat(build_messages(context, history, question))).strip()
    except Exception:  # noqa: BLE001 — chat is best-effort
        return _FALLBACK
    return reply or _FALLBACK
