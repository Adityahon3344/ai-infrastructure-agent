from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    resource: Mapped[str] = mapped_column(String, index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    request_id: Mapped[str | None] = mapped_column(String, nullable=True)
