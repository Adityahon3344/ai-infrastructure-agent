from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ServerStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"
    CRITICAL = "critical"


class Server(Base):
    """No artificial MAX_SERVERS limit — any number of rows may exist here,
    bounded only by the database itself."""

    __tablename__ = "servers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[str] = mapped_column(String, default="")
    port: Mapped[int] = mapped_column(default=22)
    username: Mapped[str] = mapped_column(String, default="")

    os_family: Mapped[str] = mapped_column(String, default="")       # e.g. linux
    os_distribution: Mapped[str] = mapped_column(String, default="")  # e.g. ubuntu
    os_version: Mapped[str] = mapped_column(String, default="")
    architecture: Mapped[str] = mapped_column(String, default="")

    environment: Mapped[str] = mapped_column(String, default="production", index=True)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)  # arbitrary key=value tags

    connection_id: Mapped[str | None] = mapped_column(ForeignKey("connections.id"), nullable=True)

    status: Mapped[ServerStatus] = mapped_column(Enum(ServerStatus), default=ServerStatus.UNKNOWN)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cpu_cores: Mapped[int | None] = mapped_column(nullable=True)
    ram_mb: Mapped[int | None] = mapped_column(nullable=True)
    disk_gb: Mapped[float | None] = mapped_column(Float, nullable=True)

    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)  # docker/python/node/etc detected
    server_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    connection = relationship("Connection", back_populates="servers")


class ServerMetricSample(Base):
    """Time-series-ish monitoring samples (pull based, gathered over SSH)."""

    __tablename__ = "server_metric_samples"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    server_id: Mapped[str] = mapped_column(String, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    ram_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_avg_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
