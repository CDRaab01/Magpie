import datetime
import uuid

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """SSO-only (CLAUDE.md §2, §8): Magpie has no password of its own. Identity comes entirely
    from dragonfly-id via POST /auth/suite, linked by email — there is deliberately no
    hashed_password column, unlike the sibling apps.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Free-form JSON blob (stored as text) for future preferences; no keys defined yet.
    settings: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
