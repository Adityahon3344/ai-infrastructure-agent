"""Password hashing, JWT issuance/verification, and Fernet-based credential
encryption. Secrets are NEVER stored in plaintext and NEVER logged."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def _fernet() -> Fernet:
    key = settings.credential_encryption_key
    if not key:
        # Derive a deterministic key from the app secret so local/dev setups work
        # out of the box without a separate key. Production deployments should set
        # CREDENTIAL_ENCRYPTION_KEY explicitly (see .env.example).
        digest = hashlib.sha256(settings.app_secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    elif isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def mask_secret(_: str) -> str:
    return "••••••••"
