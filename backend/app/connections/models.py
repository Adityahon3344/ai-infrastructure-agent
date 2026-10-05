from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, JSON, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ConnectionType(str, enum.Enum):
    SSH = "ssh"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    KUBERNETES = "kubernetes"


class ConnectionStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    VALID = "valid"
    INVALID = "invalid"
    DISABLED = "disabled"


class Connection(Base):
    """A connection stores non-secret metadata + a reference to encrypted
    credential material. Secrets are encrypted at rest (Fernet, see
    core/security.py) and are NEVER returned by the API or written to logs."""

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    type: Mapped[ConnectionType] = mapped_column(Enum(ConnectionType), nullable=False)
    status: Mapped[ConnectionStatus] = mapped_column(Enum(ConnectionStatus), default=ConnectionStatus.UNKNOWN)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Non-secret config, e.g. {"auth_method": "private_key", "region": "us-east-1"}
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Encrypted secret blob (password / private key / AWS secret key / kubeconfig).
    # Stored encrypted; only decrypted transiently in-memory at execution time.
    encrypted_credential: Mapped[str] = mapped_column(Text, default="")

    account_info: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. AWS account id, ARN
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_message: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    servers = relationship("Server", back_populates="connection")
