from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.auth.models import Role, User
from app.auth.security_deps import require_role
from app.core.database import get_db

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit_logs(limit: int = 200, db: Session = Depends(get_db), _: User = Depends(require_role(Role.ADMIN))):
    rows = db.query(AuditLog).order_by(desc(AuditLog.timestamp)).limit(min(limit, 1000)).all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "user_id": r.user_id,
            "action": r.action,
            "resource": r.resource,
            "details": r.details,
        }
        for r in rows
    ]
