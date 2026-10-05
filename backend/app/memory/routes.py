from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security_deps import get_current_user
from app.core.database import get_db
from app.memory import service as memory_service

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
def get_memory(conversation_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = memory_service.list_memory(db, user_id=user.id, conversation_id=conversation_id)
    return [{"id": i.id, "scope": i.scope.value, "key": i.key, "value": i.value, "source": i.source, "conversation_id": i.conversation_id} for i in items]


@router.delete("/{item_id}", status_code=204)
def delete_memory_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not memory_service.delete_memory(db, item_id):
        raise HTTPException(404, "Memory item not found")


@router.post("/conversations/{conversation_id}/clear")
def clear_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    count = memory_service.clear_conversation_memory(db, conversation_id)
    return {"cleared": count}
