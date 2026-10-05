from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TargetStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String, default=_uuid, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)

    prompt: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[dict] = mapped_column(JSON, default=dict)          # serialized PlanSpec
    compiled_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String, default="low")
    risk_reasons: Mapped[list] = mapped_column(JSON, default=list)

    target_server_ids: Mapped[list] = mapped_column(JSON, default=list)
    connection_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tools_used: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED, index=True)
    per_target_status: Mapped[dict] = mapped_column(JSON, default=dict)  # {server_id: TargetStatus}

    verification: Mapped[dict] = mapped_column(JSON, default=dict)
    changed_resources: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default="")

    approval_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan", order_by="JobEvent.sequence")


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    sequence: Mapped[int] = mapped_column(default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    event_type: Mapped[str] = mapped_column(String)  # job_created, planning, validation, approval_required,
    # connecting, discovery, task_started, task_output, task_completed, task_failed, verification, job_completed, job_failed
    server_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    job = relationship("Job", back_populates="events")
