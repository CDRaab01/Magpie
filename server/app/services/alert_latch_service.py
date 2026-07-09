"""Persisted alert latch (V1.md Tier 3 #21 / F11). Wraps the pure rising-edge `should_alert` with
DB-backed state, so an alert fires once per condition episode *and* the "already alerted" bit
survives a redeploy (the old process-memory latch reset on every container recreate)."""

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_latch import AlertLatch
from app.rules.alerts import should_alert


async def latched_should_alert(
    db: AsyncSession,
    user_id: uuid.UUID,
    alert_key: str,
    currently_true: bool,
    now: datetime.datetime,
) -> bool:
    """Read the stored latch for (user, alert_key), fire only on the False→True rising edge, and
    write the new state back. The caller commits. Keyed by a stable `alert_key` per condition."""
    result = await db.execute(
        select(AlertLatch).where(AlertLatch.user_id == user_id, AlertLatch.alert_key == alert_key)
    )
    latch = result.scalar_one_or_none()
    previously_true = latch.active if latch is not None else False
    fire = should_alert(currently_true, previously_true)
    if latch is None:
        # Only materialize a row once the condition is true; a never-true key stays absent.
        if currently_true:
            db.add(AlertLatch(user_id=user_id, alert_key=alert_key, active=True, updated_at=now))
    elif latch.active != currently_true:
        latch.active = currently_true
        latch.updated_at = now
    return fire
