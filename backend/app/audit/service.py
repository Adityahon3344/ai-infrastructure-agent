from __future__ import annotations

from app.core.database import session_scope
from app.core.logging_config import get_logger, redact

logger = get_logger("audit")


def record_audit_event(user_id: str | None, action: str, resource: str, details: str = "", request_id: str | None = None) -> None:
    """Append-only audit trail. Never pass secrets in `details` — this function
    also redacts common secret patterns defensively before persisting/logging."""
    from app.audit.models import AuditLog  # local import avoids circulars at module import time

    safe_details = redact(details or "")
    try:
        with session_scope() as db:
            db.add(AuditLog(user_id=user_id, action=action, resource=resource, details=safe_details, request_id=request_id))
    except Exception:
        logger.exception("Failed to persist audit event")
    logger.info(f"AUDIT action={action} resource={resource} user={user_id} details={safe_details}")
