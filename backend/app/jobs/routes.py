from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security_deps import get_current_user
from app.core.database import get_db
from app.jobs.models import Job, JobEvent

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_out(job: Job) -> dict:
    return {
        "id": job.id, "request_id": job.request_id, "conversation_id": job.conversation_id,
        "prompt": job.prompt, "plan": job.plan, "risk_level": job.risk_level, "risk_reasons": job.risk_reasons,
        "target_server_ids": job.target_server_ids, "connection_id": job.connection_id, "tools_used": job.tools_used,
        "status": job.status.value, "per_target_status": job.per_target_status, "verification": job.verification,
        "changed_resources": job.changed_resources, "error": job.error, "approval_id": job.approval_id,
        "created_at": job.created_at.isoformat(), "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("")
def list_jobs(
    status: str | None = None, server_id: str | None = None, environment: str | None = None,
    limit: int = 100, db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    rows = query.order_by(Job.created_at.desc()).limit(min(limit, 500)).all()
    if server_id:
        rows = [j for j in rows if server_id in (j.target_server_ids or [])]
    return [_job_out(j) for j in rows]


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_out(job)


@router.get("/{job_id}/events")
def get_job_events(job_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    events = db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.sequence).all()
    return [
        {"type": e.event_type, "server_id": e.server_id, "tool": e.tool, "message": e.message,
         "data": e.data, "timestamp": e.timestamp.isoformat()}
        for e in events
    ]


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.jobs.models import JobStatus
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.PARTIAL_SUCCESS):
        raise HTTPException(400, f"Cannot cancel a job in status {job.status.value}")
    job.status = JobStatus.CANCELLED
    db.commit()
    return _job_out(job)
