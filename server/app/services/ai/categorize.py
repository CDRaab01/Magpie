"""Category-suggestion drafts (CLAUDE.md §6 — the AI guardrail contract). Scope: descriptive
categorization only, never investment/tax/legal advice. The prompt sees DB-derived transaction
context (merchant, amount, kind) and the user's own category vocabulary — never a raw email,
and never anything outside this one transaction's facts. Output is Pydantic-validated; a
suggested category that isn't in the caller's own vocabulary is silently rejected, never
guessed into existence — the model may only pick from what already exists.
"""

import uuid

from pydantic import BaseModel, ValidationError

from app.services.ai.llm_client import LlmClient


class CategorySuggestion(BaseModel):
    category_name: str
    reasoning: str


def build_prompt(
    *, merchant: str | None, amount_cents: int, kind: str, category_names: list[str]
) -> str:
    dollars = abs(amount_cents) / 100
    merchant_desc = merchant or "an unlabeled transaction"
    direction = "a purchase from" if kind in ("spend", "refund") else "a deposit from"
    categories_list = ", ".join(category_names)
    return (
        f"Classify this household finance transaction into exactly one category.\n"
        f"Transaction: {direction} {merchant_desc}, amount ${dollars:.2f}.\n"
        f"Allowed categories (pick exactly one, verbatim): {categories_list}.\n"
        f'Respond with only JSON matching {{"category_name": "...", "reasoning": "..."}}.'
        f" Do not invent a category outside the allowed list."
    )


async def suggest_category(
    client: LlmClient,
    *,
    merchant: str | None,
    amount_cents: int,
    kind: str,
    categories: dict[str, uuid.UUID],
) -> uuid.UUID | None:
    """`categories` is the allowed name->id vocabulary. Returns None on any validation
    failure or an out-of-vocabulary answer — a rejected suggestion is silently absent,
    never a guessed fallback (CLAUDE.md's guardrail: the model drafts, it never decides)."""
    if not categories:
        return None
    prompt = build_prompt(
        merchant=merchant, amount_cents=amount_cents, kind=kind, category_names=list(categories)
    )
    try:
        raw = await client.complete(prompt)
        parsed = CategorySuggestion.model_validate_json(raw)
    except (ValidationError, ValueError):
        return None
    return categories.get(parsed.category_name)
