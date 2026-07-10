import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.rule import PromotionResultOut, RuleCreate, RuleOut, RuleUpdate
from app.security import CurrentUser
from app.services.rule_apply_service import (
    apply_rule_to_history,
    promote_confirmed_to_rules,
    promote_suggestions_to_rules,
)
from app.services.rule_service import create_rule, delete_rule, get_rule, list_rules, update_rule

router = APIRouter(prefix="/rules", tags=["rules"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[RuleOut])
async def all_rules(current_user: CurrentUser, db: DbSession):
    return await list_rules(db, current_user.id)


@router.post("", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
async def create_new_rule(req: RuleCreate, current_user: CurrentUser, db: DbSession):
    return await create_rule(db, current_user.id, req)


@router.post("/from-suggestions", response_model=PromotionResultOut)
async def promote_suggestions(
    current_user: CurrentUser,
    db: DbSession,
    dry_run: Annotated[bool, Query()] = True,
    min_transactions: Annotated[int, Query(ge=1)] = 1,
):
    """Turn the AI's per-merchant category drafts into deterministic `merchant_category` rules,
    and file every past transaction they match.

    **This endpoint is the human confirmation CLAUDE.md §6 requires** — the model's drafts are
    persisted as truth only because a person called this. Afterwards the LLM is out of the loop
    for those merchants: the rule files them deterministically, with an explanation.

    `dry_run=true` (the default) reports exactly what a real run would do and writes nothing.
    Merchants whose rows already carry a human-confirmed category are skipped, as are merchants
    that already have a rule — so this is safe to re-run.
    """
    summary = await promote_suggestions_to_rules(
        db, current_user.id, dry_run=dry_run, min_transactions=min_transactions
    )
    return PromotionResultOut(**dataclasses.asdict(summary))


@router.post("/from-confirmed", response_model=PromotionResultOut)
async def promote_confirmed(
    current_user: CurrentUser,
    db: DbSession,
    dry_run: Annotated[bool, Query()] = True,
    min_transactions: Annotated[int, Query(ge=1)] = 2,
):
    """Turn merchants a human has already *confirmed* a category for into `merchant_category`
    rules, so future transactions from them auto-file instead of returning to the review queue.

    The sibling of `/from-suggestions`, for after the queue is worked: those confirmations are the
    most legitimate rule source there is. A merchant split across categories is skipped (never
    guessed); already-ruled merchants are skipped (safe to re-run). `min_transactions` defaults to
    2 — a merchant seen once is a one-off and a rule for it is speculative — but can be lowered to
    1 to blanket every categorized merchant. `dry_run=true` (default) writes nothing.
    """
    summary = await promote_confirmed_to_rules(
        db, current_user.id, dry_run=dry_run, min_transactions=min_transactions
    )
    return PromotionResultOut(**dataclasses.asdict(summary))


@router.post("/{rule_id}/apply-to-history", response_model=PromotionResultOut)
async def apply_to_history(
    rule_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    dry_run: Annotated[bool, Query()] = True,
):
    """Apply one existing `merchant_category` rule to the transactions that predate it."""
    rule = await get_rule(db, current_user.id, rule_id)
    if rule.type != "merchant_category" or rule.category_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "only a merchant_category rule with a category can be applied to history",
        )
    application = await apply_rule_to_history(db, current_user.id, rule)
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return PromotionResultOut(
        dry_run=dry_run,
        rules_created=0,
        transactions_filed=application.matched,
        merchants_skipped=0,
        applications=[dataclasses.asdict(application)],
    )


@router.get("/{rule_id}", response_model=RuleOut)
async def one_rule(rule_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    return await get_rule(db, current_user.id, rule_id)


@router.patch("/{rule_id}", response_model=RuleOut)
async def patch_rule(rule_id: uuid.UUID, req: RuleUpdate, current_user: CurrentUser, db: DbSession):
    return await update_rule(db, current_user.id, rule_id, req)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_rule(rule_id: uuid.UUID, current_user: CurrentUser, db: DbSession):
    await delete_rule(db, current_user.id, rule_id)
