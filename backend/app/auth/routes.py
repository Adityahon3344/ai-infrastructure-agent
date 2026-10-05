from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit.service import record_audit_event
from app.auth.models import User
from app.auth.schemas import TokenOut, UserCreate, UserLogin, UserOut
from app.auth.security_deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    first_user = db.query(User).first() is None
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role="admin" if first_user else payload.role,  # first user bootstraps as admin
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record_audit_event(user_id=user.id, action="user_registered", resource="user", details=user.email)
    token = create_access_token(user.id, {"role": user.role.value})
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        record_audit_event(user_id=None, action="login_failed", resource="user", details=payload.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User disabled")
    record_audit_event(user_id=user.id, action="login_success", resource="user", details=user.email)
    token = create_access_token(user.id, {"role": user.role.value})
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user) if user.id != "bootstrap" else UserOut(
        id="bootstrap", email=user.email, full_name=user.full_name, role=user.role, is_active=True
    )
