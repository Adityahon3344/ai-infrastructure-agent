"""
Chat/agent memory. Two scopes:
  - short_term: current conversation's active server/connection/task/plan
  - long_term:  cross-conversation preferences (preferred server, deploy dir, etc.)

A hard rule enforced here: nothing that looks like a secret is ever stored.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.jobs.models import Job
from app.memory.models import MemoryItem, MemoryScope

_SECRET_LIKE = re.compile(r"(?i)(password|secret|private[_-]?key|access[_-]?key|token|-----BEGIN)")


class SecretInMemoryError(Exception):
    pass


def _assert_no_secret(value: str) -> None:
    if _SECRET_LIKE.search(value or ""):
        raise SecretInMemoryError("Refusing to store a value that looks like a secret in memory.")


def set_memory(db: Session, *, user_id: str | None, conversation_id: str | None, scope: MemoryScope, key: str, value: str, source: str = "") -> MemoryItem:
    _assert_no_secret(value)
    existing = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id, MemoryItem.conversation_id == (conversation_id if scope == MemoryScope.SHORT_TERM else None), MemoryItem.scope == scope, MemoryItem.key == key)
        .first()
    )
    if existing:
        existing.value = value
        existing.source = source
        db.commit()
        return existing
    item = MemoryItem(
        user_id=user_id,
        conversation_id=conversation_id if scope == MemoryScope.SHORT_TERM else None,
        scope=scope, key=key, value=value, source=source,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_memory(db: Session, *, user_id: str | None, conversation_id: str | None, key: str) -> str | None:
    item = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id, MemoryItem.conversation_id == conversation_id, MemoryItem.key == key, MemoryItem.scope == MemoryScope.SHORT_TERM)
        .first()
    )
    if item:
        return item.value
    item = db.query(MemoryItem).filter(MemoryItem.user_id == user_id, MemoryItem.key == key, MemoryItem.scope == MemoryScope.LONG_TERM).first()
    return item.value if item else None


def list_memory(db: Session, *, user_id: str | None, conversation_id: str | None = None) -> list[MemoryItem]:
    query = db.query(MemoryItem).filter(MemoryItem.user_id == user_id)
    if conversation_id:
        query = query.filter((MemoryItem.conversation_id == conversation_id) | (MemoryItem.scope == MemoryScope.LONG_TERM))
    return query.all()


def delete_memory(db: Session, item_id: str) -> bool:
    item = db.get(MemoryItem, item_id)
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def clear_conversation_memory(db: Session, conversation_id: str) -> int:
    count = db.query(MemoryItem).filter(MemoryItem.conversation_id == conversation_id, MemoryItem.scope == MemoryScope.SHORT_TERM).delete()
    db.commit()
    return count


def remember_successful_job(db: Session, job: Job) -> None:
    """Called by the executor after a successful job. Stores useful, non-secret
    context such as 'last successfully used server' and 'last deploy directory'."""
    try:
        if job.target_server_ids:
            set_memory(db, user_id=job.user_id, conversation_id=job.conversation_id, scope=MemoryScope.SHORT_TERM,
                       key="current_server_id", value=job.target_server_ids[0], source=f"job:{job.id}")
            set_memory(db, user_id=job.user_id, conversation_id=None, scope=MemoryScope.LONG_TERM,
                       key="last_successful_server_id", value=job.target_server_ids[0], source=f"job:{job.id}")
        plan = job.plan or {}
        for step in plan.get("steps", []):
            if step.get("action") == "file" and step.get("params", {}).get("state") == "directory":
                set_memory(db, user_id=job.user_id, conversation_id=None, scope=MemoryScope.LONG_TERM,
                           key="preferred_deploy_dir", value=step["params"]["path"], source=f"job:{job.id}")
    except SecretInMemoryError:
        pass
