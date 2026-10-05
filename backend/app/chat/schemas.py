from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    selected_server_ids: list[str] | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    needs_server_selection: bool = False
    server_options: list[dict] = []
    needs_connection: bool = False
    needs_clarification: bool = False
    plan_preview: dict | None = None
    job_id: str | None = None
    approval: dict | None = None
    risk_level: str | None = None
