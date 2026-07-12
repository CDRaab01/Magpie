"""Sweep pass (CLAUDE.md §5/§10): latched ntfy alerts for silent-failure conditions. Built:
unparsed-email backlog, **missing-bill** (the 'a simulated missing bill pages the phone' exit,
CLAUDE.md Phase 6), **paycheck-late**, and **per-account freshness**. Latch state is persisted
(F11) via `alert_latch_service`, so a redeploy never re-pages an already-open condition.
**Auth-hold expiry** (2026-07-10) is the first sweep that mutates data rather than only alerting;
**paycheck-short** (2026-07-10) pages when a recurring paycheck lands below its band; **bill-late**
(2026-07-11) pages when a recurring bill's expected payment is overdue (rule-driven missing-bill). **Spending
anomalies** (2026-07-10) page on a large charge at a never-seen merchant and on a category running
well over its trailing median — the proactive half of "watch my spending" (#19a).
"""

import asyncio
import datetime
import re
import logging
import uuid
from calendar import monthrange

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.account import Account
from app.models.bill_statement import BillStatement
from app.imports.pending_match import PendingCandidate, find_posted_duplicate
from app.models.ingest_event import IngestEvent
from app.models.category import Category
from app.models.rule import Rule
from app.models.transaction import COUNTABLE_STATUSES, Transaction
from app.models.user import User
from app.rules.anomaly import category_overspend, is_large_charge
from app.rules.subscriptions import price_hike_cents
from app.rules.bands import band_shortfall, median_cents
from app.rules.merchant_match import matches
from app.rules.recurrence import InvalidCadence, expected_next_date
from app.services import cross_app_client
from app.services.alert_latch_service import latched_should_alert
from app.services.ai.llm_client import LlmClient
from app.services.ai.narrate import narrate_deviation
from app.services.ingest_service import make_llm_client
from app.services.insight_service import generate_monthly_insight
from app.services.subscription_service import list_subscriptions
from app.services.rule_service import MIN_OBSERVATIONS_TO_AUTOFILE, observation_history
from app.services.ntfy_client import HttpNtfyPublisher, NtfyPublisher
from app.time_util import owner_local_date

logger = logging.getLogger("magpie.sweeps")

MISSING_BILL_GRACE_DAYS = 3

# #34: deep links carried on each alert's ntfy `Click` header. The Android app registers the
# `magpie://` scheme and routes each host to the screen that lets the owner act on the alert.
# Keep these hosts in sync with the client's MagpieNavHost deep-link routing.
LINK_BILLS = "magpie://bills"
LINK_CASHFLOW = "magpie://cashflow"
LINK_ACCOUNTS = "magpie://accounts"
LINK_HOME = "magpie://home"
LINK_SUBSCRIPTIONS = "magpie://subscriptions"
LINK_BUDGETS = "magpie://budgets"


async def count_unparsed_events(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(IngestEvent)
        .where(IngestEvent.user_id == user_id, IngestEvent.outcome == "unparsed")
    )
    return result.scalar_one()


async def run_unparsed_backlog_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """Pages once when the unparsed backlog becomes nonzero (a silent parser break). The latch is
    persisted now (F11), so a redeploy with a still-nonzero backlog doesn't re-page."""
    count = await count_unparsed_events(db, user_id)
    if await latched_should_alert(db, user_id, "unparsed_backlog", count > 0, now):
        await publisher.publish(
            f"{count} email(s) couldn't be parsed and need a look.",
            title="Magpie: unparsed email backlog",
            click=LINK_HOME,
        )


async def run_missing_bill_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    publisher: NtfyPublisher,
    *,
    now: datetime.datetime,
    grace_days: int = MISSING_BILL_GRACE_DAYS,
) -> None:
    """A `bill_statement` past its due date by `grace_days` with no matched payment pages the phone
    once (CLAUDE.md's Phase-6 exit criterion). 'Today' is owner-local (F18) so a due date isn't
    judged against a UTC wall clock. One latch per bill, so many overdue bills don't collapse into
    one alert."""
    cutoff = owner_local_date(now, settings.owner_timezone) - datetime.timedelta(days=grace_days)
    result = await db.execute(
        select(BillStatement)
        .join(Account, BillStatement.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            BillStatement.matched_transaction_id.is_(None),
            BillStatement.due_date < cutoff,
        )
    )
    for bill in result.scalars().all():
        if await latched_should_alert(db, user_id, f"missing_bill:{bill.id}", True, now):
            amount = f"${bill.amount_due / 100:,.2f}"
            await publisher.publish(
                f"{bill.biller}: {amount} was due {bill.due_date} and hasn't been paid.",
                title="Magpie: bill missing",
                click=LINK_BILLS,
            )


async def run_paycheck_late_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """A recurring-income rule whose next expected paycheck is overdue (past the cadence's
    expected date + slack, owner-local) pages once. When the paycheck lands, F6 advances the
    rule's `last_matched_at`, the expected date rolls forward, the condition goes false, and the
    latch clears — so a *later* miss is a fresh episode."""
    today = owner_local_date(now, settings.owner_timezone)
    result = await db.execute(
        select(Rule).where(
            Rule.user_id == user_id,
            Rule.type == "recurring_income",
            Rule.enabled.is_(True),
            Rule.last_matched_at.is_not(None),
        )
    )
    for rule in result.scalars().all():
        cadence = rule.cadence or {}
        try:
            expected = expected_next_date(rule.last_matched_at.date(), cadence)
        except InvalidCadence:
            continue  # a malformed cadence is a rule-editor problem, not a sweep alert
        slack = datetime.timedelta(days=cadence.get("slack_days", 0))
        late = today > expected + slack
        if await latched_should_alert(db, user_id, f"paycheck_late:{rule.id}", late, now):
            await publisher.publish(
                f"Expected income '{rule.matcher}' hasn't arrived — it was due around {expected}.",
                title="Magpie: paycheck late",
                click=LINK_CASHFLOW,
            )


async def run_bill_late_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """A recurring-bill rule whose next expected payment is overdue pages once (ROADMAP #2) — the
    "bill missing" alert driven by *rules*, not `bill_statements`. It's the analog of paycheck-late
    and the only missing-bill path until the `bill_issued` email parser lands (blocked on the
    Discover sender). When the payment lands, F6 advances the rule's `last_matched_at`, the expected
    date rolls forward, and the latch clears — so a later miss is a fresh episode."""
    today = owner_local_date(now, settings.owner_timezone)
    result = await db.execute(
        select(Rule).where(
            Rule.user_id == user_id,
            Rule.type == "recurring_bill",
            Rule.enabled.is_(True),
            Rule.last_matched_at.is_not(None),
        )
    )
    for rule in result.scalars().all():
        cadence = rule.cadence or {}
        try:
            expected = expected_next_date(rule.last_matched_at.date(), cadence)
        except InvalidCadence:
            continue
        slack = datetime.timedelta(days=cadence.get("slack_days", 0))
        late = today > expected + slack
        if await latched_should_alert(db, user_id, f"bill_late:{rule.id}", late, now):
            await publisher.publish(
                f"Expected bill '{rule.matcher}' hasn't been paid — it was due around {expected}.",
                title="Magpie: bill missing",
                click=LINK_BILLS,
            )


async def run_paycheck_short_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """A recurring-income rule whose *most recent* paycheck landed **below** its amount band pages
    once, with median context. Distinct from paycheck-late: that one is about a paycheck that never
    came; this one arrived, but light (a cut hours week, a missed bonus).

    Detected from ledger state, not at ingestion, for the same reason the other sweeps are: it
    reuses the persisted latch + publisher, and it only ever looks at the *latest* observation per
    rule — so importing three years of historical paychecks can't storm the phone with past short
    weeks. The band is computed from the *prior* observations (as it was when that paycheck was
    evaluated), and a rule needs at least `MIN_OBSERVATIONS_TO_AUTOFILE` priors before it has a
    band to be short of. The latch key carries the paycheck's own id, so each short paycheck fires
    exactly once and a later short one (a different row) is a fresh episode on its own key.
    """
    result = await db.execute(
        select(Rule).where(
            Rule.user_id == user_id,
            Rule.type == "recurring_income",
            Rule.enabled.is_(True),
        )
    )
    for rule in result.scalars().all():
        pct = (rule.amount_band or {}).get("pct")
        if pct is None or rule.account_id is None:
            continue  # no band configured, or an all-accounts income rule — nothing to be short of
        history = await observation_history(db, rule.account_id, rule.matcher)
        income = sorted(
            (t for t in history if t.kind == "income"), key=lambda t: (t.date, t.created_at)
        )
        if len(income) <= MIN_OBSERVATIONS_TO_AUTOFILE:
            continue  # need >=3 priors *plus* the latest to judge it against a real band
        latest = income[-1]
        priors = [t.amount for t in income[:-1]]
        shortfall = band_shortfall(latest.amount, priors, pct)
        key = f"paycheck_short:{rule.id}:{latest.id}"
        if await latched_should_alert(db, user_id, key, shortfall is not None, now):
            median = median_cents([abs(a) for a in priors])
            await publisher.publish(
                f"'{rule.matcher}' came in ${abs(latest.amount) / 100:,.2f} on {latest.date} — "
                f"about ${shortfall / 100:,.2f} under its ~${median / 100:,.2f} median.",
                title="Magpie: paycheck short",
                click=LINK_CASHFLOW,
            )


async def run_account_freshness_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """An account that *had* email-alert activity but none in `account_freshness_days` may have
    had its bank alerts silently turned off (the alert-decay failure mode). Keys off
    `ingest_events` — an account with no prior activity has no baseline and is skipped, so a new
    or manual-only account never false-alarms."""
    threshold = now - datetime.timedelta(days=settings.account_freshness_days)
    accounts = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.active.is_(True))
    )
    for account in accounts.scalars().all():
        latest = await db.execute(
            select(func.max(IngestEvent.received_at)).where(IngestEvent.account_id == account.id)
        )
        latest_at = latest.scalar_one()
        stale = latest_at is not None and latest_at < threshold
        if await latched_should_alert(db, user_id, f"account_stale:{account.id}", stale, now):
            await publisher.publish(
                f"No new alerts from {account.name} ({account.institution}) in "
                f"{settings.account_freshness_days}+ days — its email alerts may have stopped.",
                title="Magpie: account stale",
                click=LINK_ACCOUNTS,
            )


async def run_large_charge_sweep(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """A large spend at a merchant never seen before, within the recency window, pages once
    (ROADMAP #19a). "Never seen before" is the key that makes this proactive rather than a plain
    threshold alert on every big purchase — a large charge at your usual grocery store is not
    news; the same charge at a merchant that has never appeared is. The recency window keeps a
    three-year backfill (where every merchant is 'new' at first sight) from storming the phone.
    """
    window_start = owner_local_date(now, settings.owner_timezone) - datetime.timedelta(
        days=settings.anomaly_new_merchant_days
    )
    merchant = func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw)
    recent = (
        (
            await db.execute(
                select(Transaction)
                .join(Account, Transaction.account_id == Account.id)
                .where(
                    Account.user_id == user_id,
                    Transaction.kind == "spend",
                    Transaction.split_parent_id.is_(None),
                    Transaction.date >= window_start,
                    merchant.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for txn in recent:
        if not is_large_charge(txn.amount, settings.anomaly_large_charge_cents):
            continue
        name = (txn.merchant_norm or txn.merchant_raw or "").strip()
        if not name:
            # A nameless row (a US Bank "transaction is complete" alert carries no merchant) can't
            # be a "new merchant" — there's nothing to recognise, and reconciliation owns it.
            continue
        # First appearance = no *earlier* transaction shares this merchant. Ties on the same date
        # are broken by created_at so a same-day pair doesn't each count the other as "prior".
        earlier = await db.scalar(
            select(func.count())
            .select_from(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                func.coalesce(Transaction.merchant_norm, Transaction.merchant_raw) == name,
                Transaction.id != txn.id,
                (Transaction.date < txn.date)
                | ((Transaction.date == txn.date) & (Transaction.created_at < txn.created_at)),
            )
        )
        first_seen = earlier == 0
        if await latched_should_alert(db, user_id, f"large_new_charge:{txn.id}", first_seen, now):
            await publisher.publish(
                f"${abs(txn.amount) / 100:,.2f} at {name} on {txn.date} — a merchant Magpie "
                f"hasn't seen before.",
                title="Magpie: large charge, new merchant",
                click=LINK_HOME,
            )


async def _with_narration(llm_client, body: str, *, facts: str) -> str:
    """Append an optional LLM context line to a deviation alert body (#19). The deterministic fact
    stays first and whole; a missing/failed model just returns `body` unchanged (§6)."""
    if llm_client is None:
        return body
    line = await narrate_deviation(llm_client, facts)
    return f"{body} {line}" if line else body


async def run_category_overspend_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    publisher: NtfyPublisher,
    *,
    now: datetime.datetime,
    llm_client: LlmClient | None = None,
) -> None:
    """A category whose month-to-date spend runs well over its trailing full-month median pages
    once for the month (ROADMAP #19a) — "you've already spent more on dining this month than you
    usually spend in a whole one." Latched per (category, month), so it fires once and a later
    month is a fresh episode. Aggregated in SQL (F14); the numeric judgment is pure
    (`anomaly.category_overspend`).
    """
    today = owner_local_date(now, settings.owner_timezone)
    this_month = today.replace(day=1)
    window_start = _months_before(this_month, settings.anomaly_category_trailing_months)

    # Per (category, month-bucket) spend magnitude, in SQL. Refunds net against spend within a
    # month, matching how every other rollup treats a category (#26 semantics).
    month_bucket = func.date_trunc("month", Transaction.date)
    rows = (
        await db.execute(
            select(
                Transaction.category_id,
                month_bucket.label("m"),
                func.sum(-Transaction.amount),
            )
            .join(Account, Transaction.account_id == Account.id)
            .where(
                Account.user_id == user_id,
                Transaction.category_id.is_not(None),
                Transaction.kind.in_(("spend", "refund")),
                Transaction.is_split.is_(False),
                Transaction.status.in_(COUNTABLE_STATUSES),
                Transaction.date >= window_start,
            )
            .group_by(Transaction.category_id, "m")
        )
    ).all()

    priors: dict[uuid.UUID, list[int]] = {}
    mtd: dict[uuid.UUID, int] = {}
    for category_id, bucket, spend in rows:
        bucket_month = bucket.date() if hasattr(bucket, "date") else bucket
        if bucket_month == this_month:
            mtd[category_id] = int(spend)
        else:
            priors.setdefault(category_id, []).append(int(spend))

    names = await _category_display_names(db, user_id)
    for category_id, mtd_spend in mtd.items():
        overage = category_overspend(
            mtd_spend,
            priors.get(category_id, []),
            factor=settings.anomaly_category_factor,
            floor_cents=settings.anomaly_category_floor_cents,
            min_months=settings.anomaly_category_min_months,
        )
        key = f"category_overspend:{category_id}:{this_month:%Y-%m}"
        if await latched_should_alert(db, user_id, key, overage is not None, now):
            median = median_cents([abs(a) for a in priors[category_id]])
            name = names.get(category_id, "a category")
            body = (
                f"{name}: ${mtd_spend / 100:,.2f} so far this month — about ${overage / 100:,.2f} "
                f"over its ~${median / 100:,.2f} monthly median."
            )
            body = await _with_narration(
                llm_client,
                body,
                facts=(
                    f"Category {name} has spent ${mtd_spend / 100:,.0f} month-to-date versus a "
                    f"${median / 100:,.0f} monthly median over the last "
                    f"{len(priors[category_id])} months."
                ),
            )
            await publisher.publish(body, title="Magpie: category over its usual", click=LINK_HOME)


def _months_before(month_start: datetime.date, n: int) -> datetime.date:
    y, m = month_start.year, month_start.month
    total = (y * 12 + (m - 1)) - n
    return datetime.date(total // 12, total % 12 + 1, 1)


async def _category_display_names(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = await db.execute(
        select(Category.id, Category.name).where(
            (Category.user_id == user_id) | (Category.user_id.is_(None))
        )
    )
    return {cid: name for cid, name in rows.tuples().all()}


async def run_auth_hold_expiry_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime.datetime,
    hold_days: int | None = None,
) -> int:
    """Expire pending auth holds that never posted (CLAUDE.md §2). Returns how many were dropped.

    The first sweep that *mutates* data rather than only alerting, so it is deliberately timid:

    * The row is **kept**, not deleted — `status="expired"` plus an audit note in `rule_note`.
      The raw email survives in `ingest_events` either way, so the drop is fully reconstructible.
      Expired rows are excluded from every money query via `COUNTABLE_STATUSES`.
    * A hold with a matching **posted** transaction is never expired: it was reconciled, and the
      "same swipe" question is answered by `find_posted_duplicate` — the same tolerance the CSV
      importer and the parser replay use, so all three agree on what a match is.
    * A **human-confirmed** row is never touched. If the owner said the pending charge is real,
      a sweep does not overrule them (the F3 principle, applied to the clock).
    * A row already paired into a `transfer_group` is never touched: its partner would be left
      dangling half a group.
    * **Card accounts only.** An auth hold is a card concept. A depository "pending" is a real,
      completed debit (US Bank's own alert says "your transaction is complete") that is pending
      only because the CSV has not imported it yet — expiring those would silently delete real
      ACH activity every time the owner went a week without a reconciliation import.

    No ntfy alert: an expiring $1 pre-auth is routine, and paging for routine is how alerting
    dies. The audit note is the record.
    """
    hold_days = settings.auth_hold_days if hold_days is None else hold_days
    cutoff = owner_local_date(now, settings.owner_timezone) - datetime.timedelta(days=hold_days)

    stale = (
        (
            await db.execute(
                select(Transaction)
                .join(Account, Transaction.account_id == Account.id)
                .where(
                    Account.user_id == user_id,
                    Account.type == "card",  # an auth hold is a card concept, never a debit
                    Transaction.status == "pending",
                    Transaction.date < cutoff,
                    Transaction.review_state != "confirmed",
                    Transaction.transfer_group.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    dropped = 0
    for txn in stale:
        window_lo = txn.date - datetime.timedelta(days=3)
        window_hi = txn.date + datetime.timedelta(days=hold_days)
        posted = (
            (
                await db.execute(
                    select(Transaction.id, Transaction.amount, Transaction.date).where(
                        Transaction.account_id == txn.account_id,
                        Transaction.status == "posted",
                        Transaction.split_parent_id.is_(None),
                        Transaction.date >= window_lo,
                        Transaction.date <= window_hi,
                    )
                )
            )
            .tuples()
            .all()
        )
        candidates = [PendingCandidate(str(i), a, d) for i, a, d in posted]
        if find_posted_duplicate(txn.amount, txn.date, candidates, window_days=hold_days):
            continue  # it posted after all; reconciliation owns this row, not the clock

        txn.status = "expired"
        txn.review_state = "auto"
        txn.rule_note = f"auth hold expired: no posted match within {hold_days} days"
        dropped += 1

    if dropped:
        logger.info("Expired %d auth hold(s) for user %s", dropped, user_id)
    return dropped


async def run_budget_pace_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    publisher: NtfyPublisher,
    *,
    now: datetime.datetime,
    llm_client: LlmClient | None = None,
) -> None:
    """The coach's mid-month nudge (owner-approved): a budgeted category projecting past its own
    cap pages once per (category, month). Waits until `coach_pace_min_day` so the projection means
    something and there's month left to act; tiny budgets are floored out. All categories whose
    latch fires in ONE run are batched into a single message — setting six budgets mid-month pages
    once, not six times — while the per-category latches keep a later offender's page intact."""
    from app.rules.pace import category_pace
    from app.services.budget_service import (
        actual_spend_by_category,
        category_names,
        list_budgets,
    )

    today = owner_local_date(now, settings.owner_timezone)
    if today.day < settings.coach_pace_min_day:
        return
    this_month = today.replace(day=1)
    budgets = await list_budgets(db, user_id, this_month)
    if not budgets:
        return
    actual = await actual_spend_by_category(db, user_id, this_month)
    names = await category_names(db, user_id)
    total_days = monthrange(today.year, today.month)[1]
    days_left = total_days - today.day

    fired: list[str] = []
    fired_names: list[str] = []
    facts: list[str] = []
    for budget in budgets:
        spent = max(0, -actual.get(budget.category_id, 0))
        if spent < settings.coach_pace_floor_cents:
            continue
        pace = category_pace(
            budget.amount, spent, today.day, total_days, watch_factor=settings.coach_pace_factor
        )
        over = pace.status in ("over_pace", "over")
        key = f"budget_pace:{budget.category_id}:{this_month:%Y-%m}"
        if await latched_should_alert(db, user_id, key, over, now):
            name = names.get(budget.category_id, "Uncategorized")
            projected = pace.projected_cents if pace.projected_cents is not None else spent
            fired.append(
                f"{name}: ${spent / 100:,.2f} of ${budget.amount / 100:,.2f}"
                f" with {days_left} days left — on pace for ${projected / 100:,.2f}."
                + (
                    f" About ${pace.daily_allowance_cents / 100:,.2f}/day keeps it on budget."
                    if pace.daily_allowance_cents > 0
                    else ""
                )
            )
            facts.append(
                f"{name} spent ${spent / 100:,.0f} of its ${budget.amount / 100:,.0f} budget,"
                f" pace ${projected / 100:,.0f}"
            )
            fired_names.append(name)

    if not fired:
        return
    if len(fired) == 1:
        body, title = fired[0], "Magpie: budget over pace"
    else:
        body = f"{len(fired)} budgets over pace: " + " ".join(fired)
        title = "Magpie: budgets over pace"

    # Federated awareness Link A: when a dining-shaped budget fires, the lever fact rides along —
    # "how often did we actually cook" (reported by Cookbook). Best-effort; absence adds nothing.
    if any(re.search(r"dining|restaurant|eat(ing)? out|takeout", n, re.I) for n in fired_names):
        email = await db.scalar(select(User.email).where(User.id == user_id))
        cooked = await cross_app_client.fetch_cooked_window(email, now=now) if email else None
        if cooked is not None:
            body += (
                f" Cookbook counts {cooked.last_14_days} home-cooked meal(s) in the last 14 days"
                f" (vs {cooked.prior_14_days} the prior 14) — cooking is the lever."
            )
            facts.append(
                f"home-cooked meals: {cooked.last_14_days} last 14d vs"
                f" {cooked.prior_14_days} prior 14d"
            )

    body = await _with_narration(llm_client, body, facts="; ".join(facts))
    await publisher.publish(body, title=title, click=LINK_BUDGETS)


async def run_savings_goal_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    publisher: NtfyPublisher,
    *,
    now: datetime.datetime,
    llm_client: LlmClient | None = None,
) -> None:
    """Pages once per month when the projected month-end net falls short of the savings goal by
    more than the slack. No-op without an active goal; same min-day guard as the pace sweep (an
    early-month projection is mostly median and would cry wolf)."""
    from app.rules.pace import project_net
    from app.services.coach_service import get_goal, income_spend_medians

    goal = await get_goal(db, user_id)
    if goal is None:
        return
    today = owner_local_date(now, settings.owner_timezone)
    if today.day < settings.coach_pace_min_day:
        return
    this_month = today.replace(day=1)
    total_days = monthrange(today.year, today.month)[1]

    mtd_income, mtd_spend, median_income, median_spend = await income_spend_medians(
        db, user_id, now=now
    )
    net = project_net(
        mtd_income_cents=mtd_income,
        mtd_spend_cents=mtd_spend,
        median_income_cents=median_income,
        median_spend_cents=median_spend,
        elapsed_days=today.day,
        total_days=total_days,
    )
    short = goal.amount_cents - net.projected_net_cents
    at_risk = short > settings.coach_goal_slack_cents
    if await latched_should_alert(
        db, user_id, f"savings_goal_risk:{this_month:%Y-%m}", at_risk, now
    ):
        body = (
            f"{today:%B} is projecting ${net.projected_net_cents / 100:,.0f} net vs your"
            f" ${goal.amount_cents / 100:,.0f} savings goal — about ${short / 100:,.0f} short."
        )
        body = await _with_narration(
            llm_client,
            body,
            facts=(
                f"projected net ${net.projected_net_cents / 100:,.0f},"
                f" goal ${goal.amount_cents / 100:,.0f}, short ${short / 100:,.0f}"
            ),
        )
        await publisher.publish(body, title="Magpie: savings goal at risk", click=LINK_BUDGETS)


async def run_monthly_digest_sweep(
    db: AsyncSession,
    user_id: uuid.UUID,
    publisher: NtfyPublisher,
    *,
    now: datetime.datetime,
    llm_client: LlmClient | None = None,
) -> None:
    """Once per completed month, page a one-line "what changed" digest for the month just ended
    (ROADMAP #18's ntfy half). Latched on the summarized month, so it fires once; the LLM headline
    rides along when the model is up, and a deterministic fallback (spend/net + biggest mover)
    carries it when the model is off — the ping is never blocked on the prose (§6).
    """
    today = owner_local_date(now, settings.owner_timezone)
    prev_month = _months_before(today.replace(day=1), 1)
    key = f"monthly_digest:{prev_month:%Y-%m}"
    # The condition is simply "that month is complete" — always true once we're past it; the latch
    # turns that into exactly-once. The first sweep after a deploy sends last month's digest once.
    if not await latched_should_alert(db, user_id, key, True, now):
        return

    insight = await generate_monthly_insight(db, user_id, prev_month, llm_client=llm_client)
    spend = insight.spend_cents / 100
    net = insight.net_cents / 100
    if insight.narrative_source == "llm" and insight.narrative_summary:
        body = f"{insight.narrative_headline}. {insight.narrative_summary}"
    else:
        mover = insight.category_changes[0] if insight.category_changes else None
        move_line = ""
        if mover is not None and mover.delta_cents:
            direction = "up" if mover.delta_cents > 0 else "down"
            move_line = (
                f" {mover.category} was {direction} ${abs(mover.delta_cents) / 100:,.0f} vs usual."
            )
        body = f"Spent ${spend:,.0f}, net ${net:,.0f}.{move_line}"

    # Month-end coach verdict: did the finished month hit the savings goal, and how did the
    # budgets land? Computed from the same aggregates at digest time — no new storage.
    from app.services.budget_service import actual_spend_by_category, list_budgets
    from app.services.coach_service import get_goal

    goal = await get_goal(db, user_id)
    if goal is not None:
        verdict = "hit" if insight.net_cents >= goal.amount_cents else "missed"
        body += (
            f" Saved ${insight.net_cents / 100:,.0f} vs your"
            f" ${goal.amount_cents / 100:,.0f} goal — {verdict}."
        )
    month_budgets = await list_budgets(db, user_id, prev_month)
    if month_budgets:
        actual = await actual_spend_by_category(db, user_id, prev_month)
        overs = [
            (b, max(0, -actual.get(b.category_id, 0)) - b.amount)
            for b in month_budgets
            if max(0, -actual.get(b.category_id, 0)) > b.amount
        ]
        if overs:
            from app.services.budget_service import category_names

            names = await category_names(db, user_id)
            worst_budget, worst_over = max(overs, key=lambda pair: pair[1])
            worst_name = names.get(worst_budget.category_id, "Uncategorized")
            body += (
                f" {len(overs)} of {len(month_budgets)} budgets went over"
                f" (worst: {worst_name}, ${worst_over / 100:,.0f} over)."
            )
        else:
            body += f" All {len(month_budgets)} budgets held."
    await publisher.publish(body, title=f"Magpie: {prev_month:%B} recap", click=LINK_HOME)


async def run_subscription_sweeps(
    db: AsyncSession, user_id: uuid.UUID, publisher: NtfyPublisher, *, now: datetime.datetime
) -> None:
    """Two subscription alerts (ROADMAP #22), both latched per merchant: a **new recurrence** — a
    merchant that has become subscription-shaped and isn't already a rule — and a **price hike** —
    a subscription whose latest charge broke upward past its typical amount ("Netflix went up $3").
    Inferred from the ledger (`subscription_service`), so no rule is needed to notice the pattern.
    """
    subs = await list_subscriptions(db, user_id, now=now)
    if not subs:
        return
    known = {
        r.matcher
        for r in (
            await db.execute(
                select(Rule).where(
                    Rule.user_id == user_id,
                    Rule.type.in_(("recurring_bill", "merchant_category")),
                )
            )
        )
        .scalars()
        .all()
    }
    for sub in subs:
        rec = sub.recurrence
        is_new = not any(matches(m, sub.merchant) or matches(sub.merchant, m) for m in known)
        if await latched_should_alert(db, user_id, f"new_recurrence:{sub.merchant}", is_new, now):
            await publisher.publish(
                f"New recurring charge: ${rec.typical_amount_cents / 100:,.2f} {rec.cadence} at "
                f"{sub.merchant} (~${rec.annual_cost_cents / 100:,.0f}/yr).",
                title="Magpie: new subscription",
                click=LINK_SUBSCRIPTIONS,
            )
        hike = price_hike_cents(rec)
        key = f"price_hike:{sub.merchant}:{rec.last_amount_cents}"
        if await latched_should_alert(db, user_id, key, hike is not None, now):
            await publisher.publish(
                f"{sub.merchant} went up ${hike / 100:,.2f} — now "
                f"${rec.last_amount_cents / 100:,.2f} vs its usual "
                f"${rec.typical_amount_cents / 100:,.2f}.",
                title="Magpie: subscription price up",
                click=LINK_SUBSCRIPTIONS,
            )


async def _resolve_sweep_user_id() -> uuid.UUID | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == settings.ingest_user_email))
        user = result.scalar_one_or_none()
        return user.id if user else None


async def sweep_loop() -> None:
    """Runs until cancelled — same "log and keep going" resilience as `app/ingest/poller.py`, and
    the same rationale: a paused sweep is invisible, and a silent stale condition is exactly what
    these sweeps exist to catch."""
    publisher = HttpNtfyPublisher(settings.ntfy_base_url, settings.ntfy_topic)
    while True:
        try:
            user_id = await _resolve_sweep_user_id()
            if user_id is None:
                logger.warning(
                    "Sweep skipped: no user found for ingest_user_email=%s",
                    settings.ingest_user_email,
                )
            else:
                now = datetime.datetime.now(datetime.timezone.utc)
                async with AsyncSessionLocal() as db:
                    await run_unparsed_backlog_sweep(db, user_id, publisher, now=now)
                    await run_missing_bill_sweep(db, user_id, publisher, now=now)
                    await run_paycheck_late_sweep(db, user_id, publisher, now=now)
                    await run_bill_late_sweep(db, user_id, publisher, now=now)
                    await run_paycheck_short_sweep(db, user_id, publisher, now=now)
                    await run_large_charge_sweep(db, user_id, publisher, now=now)
                    await run_category_overspend_sweep(
                        db, user_id, publisher, now=now, llm_client=make_llm_client()
                    )
                    await run_budget_pace_sweep(
                        db, user_id, publisher, now=now, llm_client=make_llm_client()
                    )
                    await run_savings_goal_sweep(
                        db, user_id, publisher, now=now, llm_client=make_llm_client()
                    )
                    await run_account_freshness_sweep(db, user_id, publisher, now=now)
                    await run_auth_hold_expiry_sweep(db, user_id, now=now)
                    await run_monthly_digest_sweep(
                        db, user_id, publisher, now=now, llm_client=make_llm_client()
                    )
                    await run_subscription_sweeps(db, user_id, publisher, now=now)
                    await db.commit()  # persist the alert latches (F11) + any expired holds
        except Exception:
            logger.exception("Sweep failed")
        await asyncio.sleep(settings.sweep_interval_minutes * 60)
