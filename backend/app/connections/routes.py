from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit.service import record_audit_event
from app.auth.models import Role, User
from app.auth.security_deps import get_current_user, require_role
from app.connections import service
from app.connections.models import Connection
from app.connections.schemas import ConnectionCreate, ConnectionOut, ConnectionTestResult
from app.core.database import get_db

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Connection).all()


@router.post("", response_model=ConnectionOut, status_code=201)
def create_connection(payload: ConnectionCreate, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    if db.query(Connection).filter(Connection.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Connection name already exists")
    conn = service.create_connection(db, payload)
    record_audit_event(user_id=user.id, action="connection_created", resource=f"connection:{conn.id}", details=f"name={conn.name} type={conn.type.value}")
    return conn


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
def test_connection(connection_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conn = db.get(Connection, connection_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    result = service.test_connection(db, conn)
    record_audit_event(user_id=user.id, action="connection_tested", resource=f"connection:{conn.id}", details=result.message)
    return result


@router.post("/{connection_id}/disable", response_model=ConnectionOut)
def disable_connection(connection_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN))):
    conn = db.get(Connection, connection_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    conn.disabled = True
    db.commit()
    record_audit_event(user_id=user.id, action="connection_disabled", resource=f"connection:{conn.id}")
    return conn


@router.delete("/{connection_id}", status_code=204)
def delete_connection(connection_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN))):
    conn = db.get(Connection, connection_id)
    if not conn:
        raise HTTPException(404, "Connection not found")
    db.delete(conn)
    db.commit()
    record_audit_event(user_id=user.id, action="connection_deleted", resource=f"connection:{connection_id}")
