"""Transfer-pair matching (CLAUDE.md §2/§5) — pure, no I/O. A card payment is two
transactions that must net to zero across *different* accounts (the double-count trap this
whole design exists to avoid): an outflow from a depository account, an inflow onto a card.
This finds the best candidate partner for a new transaction out of a pool the caller has
already fetched from the DB (same account-scoping the caller already applies elsewhere).

**F3 — pairing is not "any two ±equal amounts on different accounts".** That rule fused a
$50 card *spend* with a coincidental $50 Zelle *deposit* into a bogus transfer (round-amount
collisions are common in real data). A transfer must be *payment-shaped*: the money leaves a
depository account (outflow, negative) and lands on a card account as a payment/credit
(inflow, positive). v1 recognizes only this card-payment shape; other internal movement
(e.g. checking↔savings) intentionally falls through to review rather than risk a false pair.
"""

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class TransferCandidate:
    id: str
    account_id: str
    account_type: str  # "card" | "depository" (CLAUDE.md §4)
    amount_cents: int
    date: datetime.date
    # Carried so the caller can honor the F3 rule "never silently rewrite a human-confirmed
    # row" — a confirmed partner is still *found* (so the new row can be routed to review) but
    # must not be auto-mutated into a transfer leg.
    review_state: str = "needs_review"


def is_card_payment_pair(a: TransferCandidate, b: TransferCandidate) -> bool:
    """True iff these two legs form a card payment (CLAUDE.md §2): different accounts, amounts
    that net to exactly zero, and the directional/type shape of a payment — the ``card`` leg is
    the positive inflow (the payment credited to the card) and the ``depository`` leg is the
    negative outflow. Requiring this shape, not merely opposite amounts, is the F3 fix that
    stops a card spend and an unrelated same-amount deposit from being fused into a transfer."""
    if a.account_id == b.account_id:
        return False
    if a.amount_cents + b.amount_cents != 0:
        return False
    card = next((leg for leg in (a, b) if leg.account_type == "card"), None)
    depository = next((leg for leg in (a, b) if leg.account_type == "depository"), None)
    if card is None or depository is None:
        return False
    return card.amount_cents > 0 and depository.amount_cents < 0


def find_transfer_match(
    candidate: TransferCandidate,
    pool: list[TransferCandidate],
    window_days: int = 3,
) -> TransferCandidate | None:
    """The closest-dated pool member that forms a card-payment pair with the candidate, within
    `window_days` either side (a payment can post to checking a day or two before/after it
    posts to the card). Exact cancellation only — partial payments fall through to review."""
    lo = candidate.date - datetime.timedelta(days=window_days)
    hi = candidate.date + datetime.timedelta(days=window_days)
    best: TransferCandidate | None = None
    best_gap: int | None = None
    for other in pool:
        if not (lo <= other.date <= hi):
            continue
        if not is_card_payment_pair(candidate, other):
            continue
        gap = abs((other.date - candidate.date).days)
        if best is None or gap < best_gap:
            best, best_gap = other, gap
    return best
