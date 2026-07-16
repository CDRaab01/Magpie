"""Household sharing (family mode) — a shared financial ledger for two adults.

The design mirrors Cookbook's list-sharing but at the *whole-ledger* level: one member (the
creator/``owner``) owns all the financial data (accounts, transactions, budgets, rules, …), and
every other member's requests resolve to that owner so both people see and act on the exact same
ledger — "full shared" (owner-confirmed). Nothing about the data model of the financial tables
changes; the resolution happens at the request boundary (see
:func:`app.services.household_service.resolve_ledger_owner_id`).

A user is in **at most one** household (the ``user_id`` unique constraint) — a person's finances
belong to one shared ledger, not several.
"""

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Household(Base):
    __tablename__ = "households"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The member whose financial data IS the household ledger; every member resolves to this id.
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HouseholdMember(Base):
    __tablename__ = "household_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    # Unique: a user belongs to one household only. The owner has a row here too (for listing).
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
