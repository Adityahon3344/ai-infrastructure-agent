from app.core.security import encrypt_secret, decrypt_secret, hash_password, verify_password, mask_secret
from app.core.logging_config import redact
from app.memory.service import set_memory, get_memory, SecretInMemoryError
from app.memory.models import MemoryScope
from app.core.database import SessionLocal


def test_credential_encryption_roundtrip():
    secret = "super-secret-value"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_password_hashing():
    hashed = hash_password("mypassword123")
    assert hashed != "mypassword123"
    assert verify_password("mypassword123", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_mask_secret_never_leaks():
    assert mask_secret("aws-secret-key-value") == "••••••••"


def test_log_redaction_strips_passwords_and_keys():
    text = "connecting with password=hunter2 and aws_secret_access_key=AKIAFAKEFAKEFAKE"
    redacted = redact(text)
    assert "hunter2" not in redacted
    assert "AKIAFAKEFAKEFAKE" not in redacted


def test_log_redaction_strips_private_keys():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc123\n-----END RSA PRIVATE KEY-----"
    redacted = redact(f"key contents: {pem}")
    assert "MIIabc123" not in redacted


def test_memory_refuses_to_store_secrets(client, auth_headers):
    db = SessionLocal()
    try:
        try:
            set_memory(db, user_id="u1", conversation_id="c1", scope=MemoryScope.SHORT_TERM, key="oops", value="password=hunter2")
            assert False, "expected SecretInMemoryError"
        except SecretInMemoryError:
            pass
    finally:
        db.close()


def test_memory_stores_and_retrieves_non_secret_preference(client, auth_headers):
    db = SessionLocal()
    try:
        set_memory(db, user_id="u1", conversation_id="c1", scope=MemoryScope.SHORT_TERM, key="current_server_id", value="srv-123")
        assert get_memory(db, user_id="u1", conversation_id="c1", key="current_server_id") == "srv-123"
    finally:
        db.close()
