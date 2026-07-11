import datetime
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Goal(Base):
    """The household's savings target (AI budget coach). One active `monthly_savings` goal — the
    number the coach projects month-end net against ("projecting $320 vs your $500 goal").

    Deliberately NOT here: per-category reduction targets. The budget *is* the category cap;
    "spend less on dining" is a lowered budget delivered as a draft, so a separate target would
    just be a second competing cap with its own pace math and alerts. `kind` exists so a future
    goal flavor is an additive enum value, not a schema change.
    """

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30), default="monthly_savings")
    amount_cents: Mapped[int] = mapped_column(BigInteger)  # net >= this, positive
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
