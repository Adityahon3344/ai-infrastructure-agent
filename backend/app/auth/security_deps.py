"""FastAPI dependencies for authentication + RBAC enforcement."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.audit.service import record_audit_event
from app.auth.models import Role, User
from app.core.database import get_db
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# Bootstrap/dev mode: if no Authorization header is supplied AND there are no
# users yet, requests are treated as the built-in admin. Once at least one user
# exists, authentication is mandatory. This lets the project run immediately
# after `docker compose up` / `uvicorn` without a chicken-and-egg signup problem,
# while still being fully secured for real deployments.


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if token:
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
        user = db.get(User, payload.get("sub"))
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
        return user

    any_user_exists = db.query(User).first() is not None
    if any_user_exists:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    # No users registered yet -> synthesize a transient admin identity so the
    # very first setup call (POST /api/auth/register) can succeed.
    return User(id="bootstrap", email="bootstrap@local", full_name="Bootstrap", role=Role.ADMIN, is_active=True)


def require_role(*roles: Role):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != Role.ADMIN:
            record_audit_event(user_id=user.id, action="authorization_denied", resource="rbac", details=f"required={roles}")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return _dep
