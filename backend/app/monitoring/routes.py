from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security_deps import get_current_user
from app.connections.models import Connection
from app.core.database import get_db
from app.monitoring import service as monitoring_service
from app.servers.models import Server

router = APIRouter(prefix="/api/servers/{server_id}/metrics", tags=["monitoring"])


@router.get("")
def get_metrics(server_id: str, history: int = 0, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if history:
        rows = monitoring_service.history(db, server_id, history)
    else:
        latest = monitoring_service.latest_metrics(db, server_id)
        rows = [latest] if latest else []
    return [
        {"timestamp": r.timestamp.isoformat(), "cpu_percent": r.cpu_percent, "ram_percent": r.ram_percent,
         "disk_percent": r.disk_percent, "load_avg_1m": r.load_avg_1m, "uptime_seconds": r.uptime_seconds}
        for r in rows
    ]


@router.post("/sample")
def sample_now(server_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    server = db.get(Server, server_id)
    if not server or not server.connection_id:
        raise HTTPException(400, "Server not found or has no connection")
    conn = db.get(Connection, server.connection_id)
    sample = monitoring_service.sample_server(db, server, conn)
    if not sample:
        raise HTTPException(502, "Failed to sample metrics (server unreachable)")
    return {"cpu_percent": sample.cpu_percent, "ram_percent": sample.ram_percent, "disk_percent": sample.disk_percent}
