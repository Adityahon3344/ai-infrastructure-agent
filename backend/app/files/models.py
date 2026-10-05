from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class FileBackup(Base):
    """Backups are taken before every write so changes can be diffed/restored."""

    __tablename__ = "file_backups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    server_id: Mapped[str] = mapped_column(String, index=True)
    remote_path: Mapped[str] = mapped_column(String, index=True)
    content_snapshot: Mapped[str] = mapped_column(Text)  # sensitive files are masked before storage, see service.py
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
