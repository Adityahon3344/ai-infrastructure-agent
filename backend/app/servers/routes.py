from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.service import record_audit_event
from app.auth.models import Role, User
from app.auth.security_deps import get_current_user, require_role
from app.connections.models import Connection
from app.connections.service import resolve_ssh_spec
from app.core.database import get_db
from app.servers.discovery import discover_server
from app.servers.models import Server, ServerStatus
from app.servers.schemas import ServerCreate, ServerOut, ServerUpdate

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("", response_model=list[ServerOut])
def list_servers(environment: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    query = db.query(Server)
    if environment:
        query = query.filter(Server.environment == environment)
    return query.all()


@router.post("", response_model=ServerOut, status_code=201)
def create_server(payload: ServerCreate, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    # No artificial MAX_SERVERS check here or anywhere else in the codebase.
    if db.query(Server).filter(Server.name == payload.name).first():
        raise HTTPException(409, "Server name already exists")
    server = Server(**payload.model_dump())
    db.add(server)
    db.commit()
    db.refresh(server)
    record_audit_event(user_id=user.id, action="server_created", resource=f"server:{server.id}", details=server.name)
    return server


@router.get("/{server_id}", response_model=ServerOut)
def get_server(server_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    return server


@router.patch("/{server_id}", response_model=ServerOut)
def update_server(server_id: str, payload: ServerUpdate, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(server, k, v)
    db.commit()
    db.refresh(server)
    record_audit_event(user_id=user.id, action="server_updated", resource=f"server:{server.id}")
    return server


@router.delete("/{server_id}", status_code=204)
def delete_server(server_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN))):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    db.delete(server)
    db.commit()
    record_audit_event(user_id=user.id, action="server_deleted", resource=f"server:{server_id}")


@router.post("/{server_id}/test")
def test_server(server_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    if not server.connection_id:
        raise HTTPException(400, "Server has no connection configured")
    conn = db.get(Connection, server.connection_id)
    spec = resolve_ssh_spec(conn, server.hostname, server.port, server.username)
    from app.tools.ssh_tool import SSHTool

    try:
        tool = SSHTool(spec)
        tool.connect()
        result = tool.run("echo ok", timeout=10)
        tool.close()
        server.status = ServerStatus.ONLINE if result.success else ServerStatus.WARNING
        server.last_seen = datetime.now(timezone.utc)
        db.commit()
        record_audit_event(user_id=user.id, action="server_tested", resource=f"server:{server.id}", details="success" if result.success else "failed")
        return {"success": result.success, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:  # noqa: BLE001
        server.status = ServerStatus.OFFLINE
        db.commit()
        return {"success": False, "error": str(exc)}


@router.post("/{server_id}/discover", response_model=ServerOut)
def discover(server_id: str, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.OPERATOR))):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    if not server.connection_id:
        raise HTTPException(400, "Server has no connection configured")
    conn = db.get(Connection, server.connection_id)
    spec = resolve_ssh_spec(conn, server.hostname, server.port, server.username)
    result = discover_server(spec)
    if not result.reachable:
        server.status = ServerStatus.OFFLINE
        db.commit()
        raise HTTPException(502, f"Discovery failed: {result.error}")

    server.os_family = result.os_family
    server.os_distribution = result.os_distribution
    server.os_version = result.os_version
    server.architecture = result.architecture
    server.cpu_cores = result.cpu_cores
    server.ram_mb = result.ram_mb
    server.disk_gb = result.disk_gb
    server.capabilities = result.capabilities
    server.server_metadata = {**server.server_metadata, "package_manager": result.package_manager, "raw": result.raw}
    server.status = ServerStatus.ONLINE
    server.last_seen = datetime.now(timezone.utc)
    db.commit()
    db.refresh(server)
    record_audit_event(user_id=user.id, action="server_discovered", resource=f"server:{server.id}")
    return server
