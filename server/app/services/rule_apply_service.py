"""Rules applied to history, and merchant drafts promoted into rules (ROADMAP Wave 3 #25).

The review-not-enter law (CLAUDE.md §1) only scales if a decision is made *once per merchant*
rather than once per transaction. A backfilled ledger has thousands of rows and ~1,250 distinct
merchants; confirming each row individually is not a product, it is data entry with extra steps.

Two operations, both `dry_run=True` by default because both write money-adjacent facts:

* `apply_rule_to_history` — a `merchant_category` rule files every past transaction it matches.
  The rule's own matcher semantics are reused (`rules.merchant_match.matches`, one-way
  containment), never re-implemented in SQL, so a rule can never mean one thing at ingest time
  and another thing here.

* `promote_suggestions_to_rules` — turns the AI's per-merchant drafts into deterministic rules.
  **This is the human's explicit confirmation step**, not an autonomous write: CLAUDE.md §6 says
  nothing the model produces is persisted without confirmation, and calling this endpoint *is*
  that confirmation. Afterwards the LLM is no longer in the loop for those merchants — the rule
  is, deterministically and explainably ("matched rule: THERESA").

Both refuse to touch a transaction that already carries a human-confirmed `category_id`. A rule
fills in blanks; it never overrules a person.
"""

import datetime
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.rules.merchant_match import matches, normalize_merchant

# Rules file spend-side rows. Income/transfer kinds are decided by the transfer matcher and the
# recurring-income rules, not by a merchant→category mapping.
CATEGORIZABLE_KINDS = ("spend", "refund")


@dataclass(frozen=True)
class RuleApplication:
    rule_id: uuid.UUID
    matcher: str
    category_name: str
    matched: int
    skipped_confirmed: int


@dataclass(frozen=True)
class PromotionSummary:
    dry_run: bool
    rules_created: int
    transactions_filed: int
    merchants_skipped: int
    applications: list[RuleApplication] = field(default_factory=list)


async def _user_account_ids(db: AsyncSession, user_id: uuid.UUID):
    return select(Account.id).where(Account.user_id == user_id)


async def _candidate_merchants(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Distinct normalized merchants on this user's transactions.

    Matching is done in Python against `matches()` rather than a SQL `LIKE`, so the rule's
    one-way-containment semantics (F8) stay defined in exactly one place.
    """
    rows = await db.execute(
        select(Transaction.merchant_norm)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id, Transaction.merchant_norm.is_not(None))
        .distinct()
    )
    return [m for (m,) in rows.tuples().all()]


async def apply_rule_to_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    rule: Rule,
    *,
    now: datetime.datetime | None = None,
    merchants: list[str] | None = None,
) -> RuleApplication:
    """File every past transaction this rule matches. Caller owns the transaction/commit.

    `merchants` is the distinct-merchant list; the bulk promoter passes it once rather than
    letting each of ~1,250 rules re-run the same DISTINCT query.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if rule.category_id is None:
        raise ValueError("a merchant_category rule needs a category to apply")

    if merchants is None:
        merchants = await _candidate_merchants(db, user_id)
    targets = [m for m in merchants if matches(rule.matcher, m)]
    category_name = await db.scalar(select(Category.name).where(Category.id == rule.category_id))

    matched = skipped = 0
    if targets:
        conds = [
            Transaction.account_id.in_(await _user_account_ids(db, user_id)),
            Transaction.merchant_norm.in_(targets),
            Transaction.kind.in_(CATEGORIZABLE_KINDS),
            Transaction.split_parent_id.is_(None),
        ]
        if rule.account_id is not None:
            conds.append(Transaction.account_id == rule.account_id)

        rows = (await db.execute(select(Transaction).where(*conds))).scalars().all()
        for txn in rows:
            if txn.category_id is not None:
                # A human already decided this row. A rule fills blanks; it never overrules.
                skipped += 1
                continue
            txn.category_id = rule.category_id
            txn.matched_rule_id = rule.id
            txn.rule_note = f"matched rule: {rule.matcher}"
            txn.review_state = "auto"
            matched += 1

    if matched:
        rule.last_matched_at = now
    return RuleApplication(
        rule_id=rule.id,
        matcher=rule.matcher,
        category_name=category_name or "(unknown)",
        matched=matched,
        skipped_confirmed=skipped,
    )


async def promote_suggestions_to_rules(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    dry_run: bool = True,
    min_transactions: int = 1,
    now: datetime.datetime | None = None,
) -> PromotionSummary:
    """Turn each merchant's AI draft into a `merchant_category` rule, then file its history.

    One rule per distinct merchant that (a) has an AI-suggested category, (b) has no
    human-confirmed category on any of its rows, and (c) meets `min_transactions`. Merchants
    that already have a rule are skipped, so this is safe to re-run.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    accounts = await _user_account_ids(db, user_id)

    # Per merchant: its draft category and how many rows it covers. A merchant whose rows
    # disagree on the draft is excluded (grouping by both makes that visible as two rows).
    grouped = (
        (
            await db.execute(
                select(
                    Transaction.merchant_norm,
                    Transaction.ai_suggested_category_id,
                    func.count().label("n"),
                    func.count(Transaction.category_id).label("confirmed"),
                )
                .where(
                    Transaction.account_id.in_(accounts),
                    Transaction.merchant_norm.is_not(None),
                    Transaction.ai_suggested_category_id.is_not(None),
                    Transaction.kind.in_(CATEGORIZABLE_KINDS),
                    Transaction.split_parent_id.is_(None),
                )
                .group_by(Transaction.merchant_norm, Transaction.ai_suggested_category_id)
            )
        )
        .tuples()
        .all()
    )

    # Merchants where a human has already categorized ANY row — including rows the AI never
    # drafted, which the `grouped` query above cannot see. If a person has expressed an opinion
    # about a merchant, a rule for it is theirs to make, not the model's. (Found on real data:
    # GOOGLE had 44 drafted rows and 5 separately-confirmed ones, and the per-group confirmed
    # count missed the latter entirely.)
    human_decided = {
        m
        for (m,) in (
            await db.execute(
                select(Transaction.merchant_norm)
                .where(
                    Transaction.account_id.in_(accounts),
                    Transaction.merchant_norm.is_not(None),
                    Transaction.category_id.is_not(None),
                    Transaction.kind.in_(CATEGORIZABLE_KINDS),
                    Transaction.split_parent_id.is_(None),
                )
                .distinct()
            )
        )
        .tuples()
        .all()
    }

    existing = {
        r.matcher
        for r in (
            await db.execute(
                select(Rule).where(Rule.user_id == user_id, Rule.type == "merchant_category")
            )
        )
        .scalars()
        .all()
    }

    seen: dict[str, int] = {}
    for merchant, _cat, n, _conf in grouped:
        seen[merchant] = seen.get(merchant, 0) + 1

    applications: list[RuleApplication] = []
    created = filed = skipped = 0
    merchants = await _candidate_merchants(db, user_id)  # fetched once, reused by every rule

    for merchant, category_id, n, confirmed in grouped:
        matcher = normalize_merchant(merchant)
        if (
            seen[merchant] > 1  # ambiguous: rows disagree on the draft
            or confirmed  # a human already categorized some of these rows
            or merchant in human_decided  # ...or any other row of this merchant
            or n < min_transactions
            or matcher in existing
            or not matcher
        ):
            skipped += 1
            continue

        rule = Rule(
            user_id=user_id,
            type="merchant_category",
            account_id=None,  # a merchant means the same thing on every account
            matcher=matcher,
            category_id=category_id,
            enabled=True,
        )
        db.add(rule)
        await db.flush()
        existing.add(matcher)
        created += 1

        application = await apply_rule_to_history(db, user_id, rule, now=now, merchants=merchants)
        filed += application.matched
        applications.append(application)

    if dry_run:
        await db.rollback()
    else:
        await db.commit()

    applications.sort(key=lambda a: -a.matched)
    return PromotionSummary(
        dry_run=dry_run,
        rules_created=created,
        transactions_filed=filed,
        merchants_skipped=skipped,
        applications=applications,
    )
