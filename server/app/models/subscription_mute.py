import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubscriptionMute(Base):
    """A merchant the owner marked "not a subscription" (ROADMAP #12). The subscription detector is
    honest but noisy — it surfaces a weekly gas stop, a Cash-App-to-a-person, and a mortgage that
    counts twice across a servicer transfer (#9). A mute makes both the Subscriptions screen and the
    two subscription sweeps (new-recurrence, price-hike) skip that merchant, without touching the
    ledger. Keyed by the same `coalesce(merchant_norm, merchant_raw)` string the detector groups on."""

    __tablename__ = "subscription_mutes"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant", name="uq_subscription_mute_user_merchant"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    merchant: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
