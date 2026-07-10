"""Rules CRUD + the evaluation orchestrator (CLAUDE.md §5). Evaluation order for every new
transaction: (1) transfer matching -> (2) recurring income/bill rules -> (3) merchant->category
rules -> (4) the LLM proposes a category as a draft only (ai_suggested_category_id, never
category_id) when `llm_client` is supplied, else falls straight to needs_review with no draft.
Dedupe happens upstream (import_service/ingest_service already dedupe before a row ever
reaches here).
"""

import datetime
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.rules.bands import is_within_band
from app.rules.merchant_match import matches, normalize_merchant
from app.rules.recurrence import is_within_cadence_window
from app.rules.transfer_matching import TransferCandidate, find_transfer_match
from app.schemas.rule import RuleCreate, RuleUpdate
from app.services.ai.categorize import suggest_category
from app.services.ai.llm_client import LlmClient

MIN_OBSERVATIONS_TO_AUTOFILE = 3

# Rule types whose cadence window is driven by `last_matched_at` (F6).
_RECURRING_RULE_TYPES = ("recurring_income", "recurring_bill")


def rule_matched_datetime(txn_date: datetime.date) -> datetime.datetime:
    """A transaction date as the UTC datetime stored in `rule.last_matched_at` (F6). The rule's
    cadence math only ever reads `.date()` back off it, so midnight UTC is the natural anchor —
    what matters is that the stored instant reflects the transaction's date, not a wall clock."""
    return datetime.datetime.combine(txn_date, datetime.time.min, tzinfo=datetime.timezone.utc)


async def advance_matched_rule_on_confirm(
    db: AsyncSession, user_id: uuid.UUID, matched_rule_id: uuid.UUID | None, txn_date: datetime.date
) -> None:
    """F6: confirming a rule-flagged transaction advances its recurring rule's window to that
    transaction's date. Without this, a single out-of-band/missed occurrence routes to review,
    the human confirms it, but the rule's `last_matched_at` never moves — so every subsequent
    occurrence reads "outside expected cadence window" forever. Advances only forward (a
    later-confirmed older row must not drag the window backward)."""
    if matched_rule_id is None:
        return
    rule = await db.get(Rule, matched_rule_id)
    if rule is None or rule.user_id != user_id or rule.type not in _RECURRING_RULE_TYPES:
        return
    matched_at = rule_matched_datetime(txn_date)
    if rule.last_matched_at is None or matched_at > rule.last_matched_at:
        rule.last_matched_at = matched_at


# --- CRUD -------------------------------------------------------------------------------


async def list_rules(db: AsyncSession, user_id: uuid.UUID) -> list[Rule]:
    result = await db.execute(select(Rule).where(Rule.user_id == user_id).order_by(Rule.matcher))
    return list(result.scalars().all())


async def create_rule(db: AsyncSession, user_id: uuid.UUID, req: RuleCreate) -> Rule:
    if req.account_id is not None:
        owned = await db.execute(
            select(Account).where(Account.id == req.account_id, Account.user_id == user_id)
        )
        if owned.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    rule = Rule(
        user_id=user_id,
        type=req.type,
        account_id=req.account_id,
        matcher=normalize_merchant(req.matcher),
        cadence=req.cadence,
        amount_band=req.amount_band,
        category_id=req.category_id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def get_rule(db: AsyncSession, user_id: uuid.UUID, rule_id: uuid.UUID) -> Rule:
    result = await db.execute(select(Rule).where(Rule.id == rule_id, Rule.user_id == user_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    return rule


async def update_rule(
    db: AsyncSession, user_id: uuid.UUID, rule_id: uuid.UUID, req: RuleUpdate
) -> Rule:
    rule = await get_rule(db, user_id, rule_id)
    if req.matcher is not None:
        rule.matcher = normalize_merchant(req.matcher)
    if req.cadence is not None:
        rule.cadence = req.cadence
    if req.amount_band is not None:
        rule.amount_band = req.amount_band
    if req.category_id is not None:
        rule.category_id = req.category_id
    if req.enabled is not None:
        rule.enabled = req.enabled
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, user_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    rule = await get_rule(db, user_id, rule_id)
    await db.delete(rule)
    await db.commit()


# --- Evaluation ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationResult:
    kind: str
    review_state: str
    category_id: uuid.UUID | None
    matched_rule_id: uuid.UUID | None
    rule_note: str | None
    # A draft only (CLAUDE.md §6 guardrail) — never set alongside category_id; stays
    # needs_review either way, since accepting it is a human action, not this evaluator's.
    ai_suggested_category_id: uuid.UUID | None = None
    transfer_group: str | None = None


async def _find_transfer_partner(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    account_type: str,
    amount_cents: int,
    txn_date: datetime.date,
) -> Transaction | None:
    """The best card-payment partner for a new leg, or None. Payment-shape (F3) needs each
    leg's account *type*, so the pool is fetched joined to Account and typed accordingly."""
    result = await db.execute(
        select(Transaction, Account.type)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.account_id != account_id,
            Transaction.transfer_group.is_(None),
            Transaction.amount == -amount_cents,
        )
    )
    rows = result.all()
    pool = [
        TransferCandidate(str(t.id), str(t.account_id), acct_type, t.amount, t.date, t.review_state)
        for t, acct_type in rows
    ]
    candidate = TransferCandidate(
        "candidate", str(account_id), account_type, amount_cents, txn_date
    )
    match = find_transfer_match(candidate, pool)
    if match is None:
        return None
    partner_result = await db.execute(
        select(Transaction).where(Transaction.id == uuid.UUID(match.id))
    )
    return partner_result.scalar_one()


async def _matching_recurring_rule(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, merchant_norm: str
) -> Rule | None:
    result = await db.execute(
        select(Rule).where(
            Rule.user_id == user_id,
            Rule.account_id == account_id,
            Rule.type.in_(("recurring_income", "recurring_bill")),
            Rule.enabled.is_(True),
        )
    )
    for rule in result.scalars().all():
        if matches(rule.matcher, merchant_norm):
            return rule
    return None


async def _matching_category_rule(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, merchant_norm: str
) -> Rule | None:
    result = await db.execute(
        select(Rule).where(
            Rule.user_id == user_id,
            Rule.type == "merchant_category",
            Rule.enabled.is_(True),
            (Rule.account_id == account_id) | (Rule.account_id.is_(None)),
        )
    )
    for rule in result.scalars().all():
        if matches(rule.matcher, merchant_norm):
            return rule
    return None


async def observation_history(
    db: AsyncSession, account_id: uuid.UUID, matcher: str
) -> list[Transaction]:
    """Every past transaction on this account whose merchant matches — includes Phase 3's
    CSV backfill history, not just transactions created after the rule existed (CLAUDE.md's
    cold-start bar counts "backfill history or live events" the same way).

    F14: the merchant substring is prefiltered in SQL (the rule's `matcher` is stored
    already-normalized, as is `merchant_norm`), so a rule evaluated against a 12-month backfill no
    longer loads + Python-normalizes the *entire* account table per row (the old O(N²)). The exact
    one-way containment check still runs in Python as the authority — the SQL `ilike` is a superset
    prefilter (a stray LIKE wildcard could only broaden it), so it can never drop a real match."""
    if not matcher:
        return []
    result = await db.execute(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.merchant_norm.isnot(None),
            Transaction.merchant_norm.ilike(f"%{matcher}%"),
        )
    )
    return [t for t in result.scalars().all() if matches(matcher, t.merchant_norm)]


async def _available_categories(db: AsyncSession, user_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """The AI's entire vocabulary (CLAUDE.md §6 guardrail) — every shared/seeded category
    plus this user's own, name -> id. The model may only pick from what's already here."""
    result = await db.execute(
        select(Category).where((Category.user_id.is_(None)) | (Category.user_id == user_id))
    )
    return {c.name: c.id for c in result.scalars().all()}


async def evaluate_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    account_id: uuid.UUID,
    amount_cents: int,
    txn_date: datetime.date,
    merchant_raw: str | None,
    default_kind: str,
    now: datetime.datetime,
    llm_client: LlmClient | None = None,
) -> EvaluationResult:
    merchant_norm = normalize_merchant(merchant_raw) if merchant_raw else None

    # 1. Transfer matching — deterministic, no review needed, wins outright. Payment-shape (F3)
    #    depends on the account's type, so fetch it before searching for a partner.
    account_type = await db.scalar(
        select(Account.type).where(Account.id == account_id, Account.user_id == user_id)
    )
    partner = await _find_transfer_partner(
        db, user_id, account_id, account_type, amount_cents, txn_date
    )
    if partner is not None:
        # F3: never silently rewrite a human-confirmed row into a transfer leg. A confirmed
        # partner routes the NEW row to review (with the pairing named) and is left untouched;
        # the human can un-pair/repair deliberately. Only unconfirmed partners auto-pair.
        if partner.review_state == "confirmed":
            return EvaluationResult(
                kind=default_kind,
                review_state="needs_review",
                category_id=None,
                matched_rule_id=None,
                rule_note="Looks like a transfer to a confirmed transaction — pair manually",
            )
        group = str(uuid.uuid4())
        partner.kind = "transfer"
        partner.transfer_group = group
        partner.review_state = "auto"
        return EvaluationResult(
            kind="transfer",
            review_state="auto",
            category_id=None,
            matched_rule_id=None,
            rule_note="Matched transfer pair",
            transfer_group=group,
        )

    if merchant_norm is None:
        return EvaluationResult(
            kind=default_kind,
            review_state="needs_review",
            category_id=None,
            matched_rule_id=None,
            rule_note=None,
        )

    # 2. Recurring income/bill rules — cold-start gated on >=3 observations, then cadence +
    #    amount band both have to hold before auto-filing.
    recurring = await _matching_recurring_rule(db, user_id, account_id, merchant_norm)
    if recurring is not None:
        history = await observation_history(db, account_id, recurring.matcher)
        observations = len(history)
        # The amount's sign, not the rule type, decides kind — a rule only recognizes *which*
        # recurring thing this is (for cadence/band/category), never overrides the ledger's
        # sign invariant (CLAUDE.md's classify.py is the single source of truth for that).
        kind = default_kind

        if observations < MIN_OBSERVATIONS_TO_AUTOFILE:
            note = f"Looks like {recurring.matcher}, {observations}/{MIN_OBSERVATIONS_TO_AUTOFILE} observations"
            return EvaluationResult(
                kind=kind,
                review_state="needs_review",
                category_id=recurring.category_id,
                matched_rule_id=recurring.id,
                rule_note=note,
            )

        cadence_ok = True
        if recurring.cadence and recurring.last_matched_at is not None:
            cadence_ok = is_within_cadence_window(
                recurring.last_matched_at.date(), txn_date, recurring.cadence
            )
        band_ok = True
        if recurring.amount_band and recurring.amount_band.get("pct") is not None:
            band_ok = is_within_band(
                amount_cents, [t.amount for t in history], recurring.amount_band["pct"]
            )

        if cadence_ok and band_ok:
            # F6: anchor the rule's window to the matched transaction's DATE, not wall-clock
            # `now` — a delayed import (a backfill row dated weeks ago) must not push the
            # cadence window to today and desync every future occurrence.
            recurring.last_matched_at = rule_matched_datetime(txn_date)
            return EvaluationResult(
                kind=kind,
                review_state="auto",
                category_id=recurring.category_id,
                matched_rule_id=recurring.id,
                rule_note=f"Matched rule: {recurring.matcher}",
            )
        reason = "out of band" if not band_ok else "outside expected cadence window"
        return EvaluationResult(
            kind=kind,
            review_state="needs_review",
            category_id=recurring.category_id,
            matched_rule_id=recurring.id,
            rule_note=f"{recurring.matcher}: {reason}",
        )

    # 3. Merchant -> category rules — deterministic category assignment, no ambiguity.
    category_rule = await _matching_category_rule(db, user_id, account_id, merchant_norm)
    if category_rule is not None:
        return EvaluationResult(
            kind=default_kind,
            review_state="auto",
            category_id=category_rule.category_id,
            matched_rule_id=category_rule.id,
            rule_note=f"Matched rule: {category_rule.matcher}",
        )

    # 4. Nothing deterministic matched — the LLM proposes a category as a draft only
    #    (CLAUDE.md §6): it is NEVER written to category_id, only ai_suggested_category_id,
    #    and review_state stays needs_review regardless — accepting a draft is a human action.
    ai_suggested = None
    if llm_client is not None:
        available = await _available_categories(db, user_id)
        ai_suggested = await suggest_category(
            llm_client,
            merchant=merchant_raw,
            amount_cents=amount_cents,
            kind=default_kind,
            categories=available,
        )

    return EvaluationResult(
        kind=default_kind,
        review_state="needs_review",
        category_id=None,
        matched_rule_id=None,
        rule_note=None,
        ai_suggested_category_id=ai_suggested,
    )
