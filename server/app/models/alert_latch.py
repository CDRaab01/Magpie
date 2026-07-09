import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlertLatch(Base):
    """Persisted alert-latch state (F11). A deviation alert must fire once per condition
    *episode*, not once per sweep — and that "did we already alert?" bit must survive a redeploy,
    or every restart re-pages the phone for a still-open condition. The old sweep carried it in
    process memory (`previously_true`), which reset on every container recreate; this stores it as
    data, keyed by a stable `alert_key` per condition (e.g. `unparsed_backlog`,
    `missing_bill:<bill_id>`, `paycheck_late:<rule_id>`, `account_stale:<account_id>`).
    """

    __tablename__ = "alert_latches"
    __table_args__ = (UniqueConstraint("user_id", "alert_key", name="uq_alert_latch_user_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    alert_key: Mapped[str] = mapped_column(String(255))
    # Whether the condition was true at the last check — the latch. A rising edge (False→True)
    # is the only thing that fires.
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
