from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.service import record_audit_event
from app.auth.models import Role, User
from app.auth.security_deps import get_current_user, require_role
from app.automations.models import Automation
from app.automations.scheduler import schedule_automation, unschedule_automation
from app.core.database import get_db

router = APIRouter(prefix="/api/automations", tags=["automations"])


class AutomationCreate(BaseModel):
    name: str
    prompt: str
    target_server_ids: list[str] = []
    cron_expression: str  # e.g. "0 2 * * *" = every day at 02:00


@router.get("")
def list_automations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Automation).filter(Automation.user_id == user.id).all()
    return [
        {"id": a.id, "name": a.name, "prompt": a.prompt, "cron_expression": a.cron_expression, "enabled": a.enabled,
         "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None, "last_job_id": a.last_job_id}
        for a in rows
    ]


@router.post("", status_code=201)
def create_automation(payload: AutomationCreate, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    automation = Automation(user_id=user.id, **payload.model_dump())
    db.add(automation)
    db.commit()
    db.refresh(automation)
    try:
        schedule_automation(automation.id, automation.cron_expression)
    except ValueError as exc:
        db.delete(automation)
        db.commit()
        raise HTTPException(400, str(exc))
    record_audit_event(user_id=user.id, action="automation_created", resource=f"automation:{automation.id}", details=automation.name)
    return {"id": automation.id}


@router.post("/{automation_id}/toggle")
def toggle_automation(automation_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    automation = db.get(Automation, automation_id)
    if not automation:
        raise HTTPException(404, "Automation not found")
    automation.enabled = not automation.enabled
    db.commit()
    if automation.enabled:
        schedule_automation(automation.id, automation.cron_expression)
    else:
        unschedule_automation(automation.id)
    return {"enabled": automation.enabled}


@router.delete("/{automation_id}", status_code=204)
def delete_automation(automation_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    automation = db.get(Automation, automation_id)
    if not automation:
        raise HTTPException(404, "Automation not found")
    unschedule_automation(automation_id)
    db.delete(automation)
    db.commit()
