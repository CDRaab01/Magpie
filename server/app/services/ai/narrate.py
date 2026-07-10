"""Deviation-alert narration (ROADMAP #19) — an optional one-line LLM gloss appended to a
deviation alert, under the §6 guardrail. The deterministic fact always comes first and stands on
its own; this only adds colour ("the last time dining ran this high was March"). Best-effort: a
missing or misbehaving model yields None, and the alert goes out with just the fact.
"""

from app.services.ai.llm_client import LlmClient

_MAX_CHARS = 140


async def narrate_deviation(client: LlmClient, facts: str) -> str | None:
    """One short, descriptive sentence of context for a deviation, or None. `facts` is the
    deterministic aggregate context (already-computed numbers, never a raw row). The model may
    only rephrase/contextualize; it never invents a figure, and the caller keeps the fact line
    regardless (§6: descriptive, never advisory)."""
    prompt = (
        "Add ONE short, factual sentence of context to this household-finance alert. Use only the "
        "facts given, invent no numbers, give no advice, and do not repeat the alert verbatim. "
        f"Keep it under {_MAX_CHARS} characters.\n\nAlert facts: {facts}\n\nContext sentence:"
    )
    try:
        line = (await client.complete(prompt)).strip().strip('"')
    except Exception:  # noqa: BLE001 — narration is strictly optional
        return None
    if not line:
        return None
    # A model that ignores the length cap gets truncated rather than trusted to be terse.
    return line[:_MAX_CHARS].rstrip()
