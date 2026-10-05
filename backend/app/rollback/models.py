from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class DeploymentVersion(Base):
    """One row per successful deploy to a given server+path. Enables
    'redeploy previous version' rollback for application deployments."""

    __tablename__ = "deployment_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    server_id: Mapped[str] = mapped_column(String, index=True)
    deploy_path: Mapped[str] = mapped_column(String, index=True)
    job_id: Mapped[str] = mapped_column(String, index=True)
    repo_url: Mapped[str] = mapped_column(String, default="")
    git_ref: Mapped[str] = mapped_column(String, default="")  # commit SHA or tag, captured post-deploy
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
