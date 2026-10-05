from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    ADMIN = "admin"          # full access incl. connections, approvals, user mgmt
    OPERATOR = "operator"    # can run automation, needs approval for HIGH risk
    VIEWER = "viewer"        # read-only: chat read, jobs read, monitoring read


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String, default="")
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.OPERATOR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    server_permissions = relationship("ServerPermission", back_populates="user", cascade="all, delete-orphan")


class ServerPermission(Base):
    """Server-level access control: which users may target which servers."""

    __tablename__ = "server_permissions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    server_id: Mapped[str] = mapped_column(String, index=True)
    can_execute: Mapped[bool] = mapped_column(Boolean, default=True)
    can_approve_high_risk: Mapped[bool] = mapped_column(Boolean, default=False)

    user = relationship("User", back_populates="server_permissions")
