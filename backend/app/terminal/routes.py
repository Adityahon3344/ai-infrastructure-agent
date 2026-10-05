from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth.models import Role, User
from app.auth.security_deps import require_role
from app.connections.models import Connection
from app.core.database import SessionLocal, get_db
from app.servers.models import Server
from app.terminal import service as terminal_service

router = APIRouter(prefix="/api/servers/{server_id}/terminal", tags=["terminal"])


@router.websocket("/ws")
async def terminal_ws(websocket: WebSocket, server_id: str):
    await websocket.accept()
    db: Session = SessionLocal()
    try:
        server = db.get(Server, server_id)
        if not server or not server.connection_id:
            await websocket.send_json({"type": "error", "message": "Server not found or has no connection"})
            await websocket.close()
            return
        connection = db.get(Connection, server.connection_id)

        while True:
            data = await websocket.receive_json()
            command = data.get("command", "")

            def on_output(stream: str, line: str):
                import asyncio
                from app.core.loop_registry import get_main_loop
                asyncio.run_coroutine_threadsafe(websocket.send_json({"type": stream, "line": line}), get_main_loop())

            result = terminal_service.run_command(server, connection, command, None, on_output, timeout=60)
            await websocket.send_json({"type": "result", **result})
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
