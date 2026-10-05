from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Automation(Base):
    """A saved automation replays a natural-language prompt on a cron schedule
    through the exact same agent pipeline as an interactive chat message —
    same validation, same risk classification, same approval requirement for
    HIGH-risk actions (a scheduled HIGH-risk automation still creates an
    ApprovalRequest rather than silently executing)."""

    __tablename__ = "automations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(Text)
    target_server_ids: Mapped[list] = mapped_column(JSON, default=list)
    cron_expression: Mapped[str] = mapped_column(String)  # standard 5-field cron
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
