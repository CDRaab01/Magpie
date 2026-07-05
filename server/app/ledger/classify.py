"""Signed-cents classification rules (CLAUDE.md §2, ARCHITECTURE.md's `app/ledger/`).

Pure, no I/O — every function here takes plain values and returns a plain value or raises
`ValueError`. This is the app's correctness core: if a number is wrong on the phone, the bug
is here or in what feeds it, never in Kotlin (CLAUDE.md invariant).

**Sign convention** (derived from CLAUDE.md's stated semantics, made explicit here since the
spec describes behavior, not numeric sign):
  - ``spend``    → amount < 0 (money leaving an account)
  - ``income``   → amount > 0 (money entering an account)
  - ``refund``   → amount > 0 (money returning) but excluded from the "income" rollup and
                   summed alongside "spend" in category totals — a refund in the same
                   category as its original purchase nets the spend down arithmetically,
                   without ever counting as income (CLAUDE.md §2: "card refunds are negative
                   spend in the original category, never income").
  - ``transfer`` → either sign per leg (an outflow leg is negative, the matching inflow leg
                   positive); the two legs of one ``transfer_group`` must sum to exactly zero
                   (CLAUDE.md §2: "card payments are transfers... nets to zero" — the
                   double-count trap this whole design exists to avoid).
"""

TRANSACTION_KINDS = ("spend", "income", "transfer", "refund")


def validate_kind_amount_sign(kind: str, amount: int) -> None:
    """Raise ValueError if `amount`'s sign doesn't match what `kind` requires.

    Called at the write boundary (schema/service layer) — this is the enforcement point for
    the sign convention above; nothing downstream should have to re-derive it.
    """
    if kind not in TRANSACTION_KINDS:
        raise ValueError(f"Unknown transaction kind: {kind!r}")
    if amount == 0:
        raise ValueError("Transaction amount must be nonzero")
    if kind == "spend" and amount >= 0:
        raise ValueError("A 'spend' transaction must have a negative amount")
    if kind == "income" and amount <= 0:
        raise ValueError("An 'income' transaction must have a positive amount")
    if kind == "refund" and amount <= 0:
        raise ValueError("A 'refund' transaction must have a positive amount")
    # "transfer" has no sign constraint — either leg may be the outflow or inflow side.


def validate_transfer_pair(amount_a: int, amount_b: int) -> None:
    """Raise ValueError unless the two legs of a transfer_group net to exactly zero.

    Not yet wired to a caller in Phase 2 (auto transfer-matching is the rules engine's job,
    CLAUDE.md §5/Phase 5) — this is the invariant the matcher must uphold when it lands,
    tested now so the rule is pinned before anything depends on it.
    """
    if amount_a + amount_b != 0:
        raise ValueError(
            f"Transfer pair does not net to zero: {amount_a} + {amount_b} = {amount_a + amount_b}"
        )
