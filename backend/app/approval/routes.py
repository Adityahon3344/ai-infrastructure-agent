from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approval import service as approval_service
from app.approval.models import ApprovalRequest, ApprovalStatus
from app.audit.service import record_audit_event
from app.auth.models import Role, User
from app.auth.security_deps import get_current_user, require_role
from app.core.database import SessionLocal, get_db
from app.jobs.models import Job, JobStatus

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class DecisionPayload(BaseModel):
    note: str = ""


@router.get("")
def list_approvals(status: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = db.query(ApprovalRequest)
    if status:
        query = query.filter(ApprovalRequest.status == status)
    rows = query.order_by(ApprovalRequest.created_at.desc()).all()
    return [
        {
            "id": r.id, "job_id": r.job_id, "action_summary": r.action_summary, "target_summary": r.target_summary,
            "expected_changes": r.expected_changes, "risk_level": r.risk_level, "impact": r.impact,
            "status": r.status.value, "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/{approval_id}/approve")
def approve(approval_id: str, payload: DecisionPayload, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    req = approval_service.decide(db, approval_id, True, user.id, payload.note)
    record_audit_event(user_id=user.id, action="approval_granted", resource=f"approval:{req.id}", details=req.action_summary)

    job = db.get(Job, req.job_id)
    from app.execution.executor import execute_job
    from app.chat.service import get_or_create_event_loop
    import threading

    loop = get_or_create_event_loop()
    threading.Thread(target=execute_job, args=(job.id, SessionLocal, loop), daemon=True).start()
    return {"status": "approved", "job_id": job.id}


@router.post("/{approval_id}/reject")
def reject(approval_id: str, payload: DecisionPayload, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    req = approval_service.decide(db, approval_id, False, user.id, payload.note)
    job = db.get(Job, req.job_id)
    job.status = JobStatus.CANCELLED
    db.commit()
    record_audit_event(user_id=user.id, action="approval_rejected", resource=f"approval:{req.id}", details=payload.note)
    return {"status": "rejected", "job_id": job.id}
