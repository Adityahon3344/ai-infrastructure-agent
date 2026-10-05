from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MemoryScope(str, enum.Enum):
    SHORT_TERM = "short_term"   # tied to one conversation
    LONG_TERM = "long_term"     # persists across conversations for a user


class MemoryItem(Base):
    """Non-secret memory only. Secrets (passwords, keys, tokens) must never be
    written here — see memory/service.py which enforces a keyword scan before
    persisting anything."""

    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    scope: Mapped[MemoryScope] = mapped_column(Enum(MemoryScope), default=MemoryScope.SHORT_TERM)
    key: Mapped[str] = mapped_column(String, index=True)   # e.g. "current_server", "preferred_deploy_dir"
    value: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="")  # e.g. "chat", "job:123"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
