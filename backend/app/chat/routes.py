from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import handle_message
from app.auth.models import User
from app.auth.security_deps import get_current_user
from app.chat.models import Conversation, Message, MessageRole
from app.chat.schemas import ChatRequest, ChatResponse
from app.core.database import get_db

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
    if not conversation:
        conversation = Conversation(user_id=user.id, title=payload.message[:60])
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(Message(conversation_id=conversation.id, role=MessageRole.USER, content=payload.message))
    db.commit()

    result = handle_message(
        db, user_id=user.id, conversation_id=conversation.id, text=payload.message,
        selected_server_ids=payload.selected_server_ids,
    )

    db.add(Message(
        conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=result.message,
        meta={
            "plan_preview": result.plan_preview, "job_id": result.job_id, "approval": result.approval,
            "server_options": result.server_options, "risk_level": result.risk_level,
        },
    ))
    db.commit()

    return ChatResponse(conversation_id=conversation.id, **{k: v for k, v in result.__dict__.items()})


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()} for c in rows]


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at).all()
    return [{"id": m.id, "role": m.role.value, "content": m.content, "meta": m.meta, "created_at": m.created_at.isoformat()} for m in rows]
