from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.service import record_audit_event
from app.auth.models import Role, User
from app.auth.security_deps import get_current_user, require_role
from app.connections.models import Connection
from app.core.database import get_db
from app.files import service as file_service
from app.servers.models import Server

router = APIRouter(prefix="/api/servers/{server_id}/files", tags=["files"])


def _server_and_conn(db: Session, server_id: str) -> tuple[Server, Connection]:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    if not server.connection_id:
        raise HTTPException(400, "Server has no connection configured")
    conn = db.get(Connection, server.connection_id)
    return server, conn


@router.get("")
def browse(server_id: str, path: str = "/", db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    server, conn = _server_and_conn(db, server_id)
    try:
        return file_service.browse(server, conn, path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/view")
def view(server_id: str, path: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    server, conn = _server_and_conn(db, server_id)
    try:
        return file_service.view_file(server, conn, path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


class WritePayload(BaseModel):
    path: str
    content: str


@router.post("/write")
def write(server_id: str, payload: WritePayload, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    server, conn = _server_and_conn(db, server_id)
    try:
        result = file_service.write_file(db, server, conn, payload.path, payload.content, user.id)
        record_audit_event(user_id=user.id, action="file_written", resource=f"server:{server_id}:{payload.path}")
        return result
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/backups")
def backups(server_id: str, path: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = file_service.list_backups(db, server_id, path)
    return [{"id": b.id, "path": b.remote_path, "created_at": b.created_at.isoformat(), "created_by": b.created_by} for b in rows]


@router.post("/backups/{backup_id}/restore")
def restore(server_id: str, backup_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    server, conn = _server_and_conn(db, server_id)
    try:
        result = file_service.restore_backup(db, server, conn, backup_id)
        record_audit_event(user_id=user.id, action="file_restored", resource=f"server:{server_id}:backup:{backup_id}")
        return result
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))
