from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.approval.models import ApprovalRequest, ApprovalStatus
from app.jobs.models import Job, JobStatus
from app.planner.planspec import PlanSpec
from app.risk.classifier import RiskAssessment


def create_approval_request(db: Session, job: Job, plan: PlanSpec, risk: RiskAssessment, requested_by: str | None) -> ApprovalRequest:
    target_summary = (
        f"{len(plan.target.server_ids)} server(s)" if plan.target.kind == "servers" else f"cloud connection {plan.target.connection_id}"
    )
    req = ApprovalRequest(
        job_id=job.id,
        requested_by=requested_by,
        action_summary=plan.summary,
        target_summary=target_summary,
        expected_changes=plan.expected_changes,
        risk_level=risk.level.value,
        impact="; ".join(risk.reasons),
    )
    db.add(req)
    job.status = JobStatus.WAITING_FOR_APPROVAL
    job.approval_id = req.id
    db.commit()
    db.refresh(req)
    return req


def decide(db: Session, approval_id: str, approve: bool, decided_by: str, note: str = "") -> ApprovalRequest:
    req = db.get(ApprovalRequest, approval_id)
    if not req:
        raise ValueError("Approval request not found")
    if req.status != ApprovalStatus.PENDING:
        raise ValueError(f"Approval already decided: {req.status.value}")
    req.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    req.decided_by = decided_by
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = note
    db.commit()
    db.refresh(req)
    return req
