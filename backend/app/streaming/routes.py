from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.jobs.models import JobEvent
from app.streaming.manager import stream_manager

router = APIRouter(tags=["streaming"])


@router.websocket("/ws/jobs/{job_id}")
async def job_stream(websocket: WebSocket, job_id: str):
    await websocket.accept()

    db: Session = SessionLocal()
    try:
        history = db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.sequence).all()
        for ev in history:
            await websocket.send_json({
                "type": ev.event_type, "job_id": job_id, "server_id": ev.server_id,
                "tool": ev.tool, "message": ev.message, "data": ev.data,
                "timestamp": ev.timestamp.isoformat(), "replay": True,
            })
    finally:
        db.close()

    queue = await stream_manager.subscribe(job_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") in ("job_completed", "job_failed", "job_cancelled"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await stream_manager.unsubscribe(job_id, queue)
