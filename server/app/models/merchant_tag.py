import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MerchantTag(Base):
    """A user-applied label on a merchant that unlocks a cross-app affordance (federated awareness
    Link G). v1 has one tag, ``"fitness"``: tagging a gym membership tells Magpie to fetch this
    month's training-day count from Spotter and show the subscription's cost-per-visit. Kept
    separate from the ledger and from mutes — a tag adds context, it never hides a row. Keyed by
    the same ``coalesce(merchant_norm, merchant_raw)`` string the subscription detector groups on,
    exactly like ``subscription_mutes``."""

    __tablename__ = "merchant_tags"
    __table_args__ = (
        UniqueConstraint("user_id", "merchant", "tag", name="uq_merchant_tag_user_merchant_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    merchant: Mapped[str] = mapped_column(String(255))
    tag: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
