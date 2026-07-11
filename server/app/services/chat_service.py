"""Ask-your-ledger chat service (ROADMAP #21): assemble the trusted aggregate context and answer.

The context is DB-derived rollups only — monthly income/spend/net, per-category spend for the last
few months (so "dining vs May" works), top merchants, and the subscriptions total. Never a raw
transaction row (§6). Everything here is aggregated in SQL (F14).
"""

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.services.ai.chat import answer, validate_user_message
from app.services.ai.llm_client import LlmClient
from app.services.subscription_service import list_subscriptions
from app.services.summary_service import spending_history, top_merchants

CONTEXT_MONTHS = 6


async def build_ledger_context(
    db: AsyncSession, user_id: uuid.UUID, *, now: datetime.datetime
) -> dict:
    """The trusted aggregate context for a chat turn — rollups only, no raw rows."""
    today = now.date()
    this_month = today.replace(day=1)

    history = await spending_history(db, user_id, months=CONTEXT_MONTHS, now=now)
    monthly = [
        {
            "month": f"{m.year:04d}-{m.month:02d}",
            "income": round(m.income_cents / 100, 2),
            "spend": round(m.spend_cents / 100, 2),
            "net": round(m.net_cents / 100, 2),
        }
        for m in history
    ]

    # Per-(category, month) spend for the last few months, so comparisons across months answer.
    total = this_month.year * 12 + (this_month.month - 1)
    window_start = datetime.date((total - 3) // 12, (total - 3) % 12 + 1, 1)
    month_bucket = func.date_trunc("month", Transaction.date)
    rows = (
        await db.execute(
            select(Category.name, month_bucket, func.sum(-Transaction.amount))
            .select_from(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .join(Category, Transaction.category_id == Category.id)
            .where(
                Account.user_id == user_id,
                Transaction.kind.in_(("spend", "refund")),
                Transaction.is_split.is_(False),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= window_start,
            )
            .group_by(Category.name, month_bucket)
        )
    ).all()
    category_by_month: dict[str, dict[str, float]] = {}
    for name, bucket, spend in rows:
        bucket_month = bucket.date() if hasattr(bucket, "date") else bucket
        key = f"{bucket_month.year:04d}-{bucket_month.month:02d}"
        category_by_month.setdefault(key, {})[name] = round(int(spend) / 100, 2)

    merchants = await top_merchants(db, user_id, this_month, limit=8)
    subs = await list_subscriptions(db, user_id, now=now)

    # The coach's full budget table + goal (§6 amendment) — the SAME per-category context the
    # /coach endpoints see (never truncated), so "how are the budgets?" and "analyze dining"
    # are groundable. Reused, not recomputed.
    from app.services.coach_service import build_coach_status, coach_status_payload

    coach = coach_status_payload(await build_coach_status(db, user_id, now=now))

    return {
        "as_of": today.isoformat(),
        "monthly_income_spend_net": monthly,
        "category_spend_by_month": category_by_month,
        "top_merchants_this_month": [
            {"merchant": m, "spend": round(-cents / 100, 2)} for m, cents, _n in merchants
        ],
        "recurring_annual_total": round(sum(s.recurrence.annual_cost_cents for s in subs) / 100, 2),
        "budgets_this_month": coach["budgets"],
        "net_projection": coach["net"],
        "savings_goal": coach["savings_goal"],
        "uncategorized_mtd": coach["uncategorized_mtd"],
    }


async def answer_question(
    db: AsyncSession,
    user_id: uuid.UUID,
    question: str,
    history: list[dict],
    *,
    llm_client: LlmClient | None,
    now: datetime.datetime,
) -> tuple[str | None, str]:
    """Answer one chat turn. Returns (error, reply): a validation error (with an empty reply) or
    (None, reply). A missing model is a reply, not an error — the endpoint stays 200 and the UI
    shows the "can't answer right now" line."""
    error = validate_user_message(question)
    if error is not None:
        return error, ""
    for turn in history:
        if turn.get("role") == "user" and (e := validate_user_message(turn.get("content", ""))):
            return e, ""  # injection/oversize can hide in earlier turns, not just the latest
    if llm_client is None:
        return None, "Chat isn't available — the local model isn't configured."
    context = await build_ledger_context(db, user_id, now=now)
    return None, await answer(llm_client, context, history, question)
