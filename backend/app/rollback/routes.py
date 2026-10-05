from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.service import record_audit_event
from app.auth.models import Role, User
from app.auth.security_deps import get_current_user, require_role
from app.connections.models import Connection
from app.core.database import get_db
from app.rollback import service as rollback_service
from app.servers.models import Server

router = APIRouter(prefix="/api/servers/{server_id}/deployments", tags=["rollback"])


@router.get("")
def list_deployments(server_id: str, deploy_path: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    versions = rollback_service.list_versions(db, server_id, deploy_path)
    return [{"id": v.id, "job_id": v.job_id, "repo_url": v.repo_url, "git_ref": v.git_ref, "created_at": v.created_at.isoformat()} for v in versions]


@router.post("/{version_id}/rollback")
def rollback(server_id: str, version_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    server = db.get(Server, server_id)
    if not server or not server.connection_id:
        raise HTTPException(400, "Server not found or has no connection")
    conn = db.get(Connection, server.connection_id)
    try:
        result = rollback_service.rollback_deployment(db, server, conn, version_id)
        record_audit_event(user_id=user.id, action="deployment_rollback", resource=f"server:{server_id}:version:{version_id}")
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))
