"""Connection lifecycle: create (encrypt secret), test, resolve credentials for
execution. This is the ONLY module allowed to decrypt credential material, and
it never returns secrets to callers outside the tool layer."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.connections.models import Connection, ConnectionStatus, ConnectionType
from app.connections.schemas import ConnectionCreate, ConnectionTestResult
from app.core.security import decrypt_secret, encrypt_secret
from app.tools.ssh_tool import SSHConnectionSpec, SSHTool


def _secret_payload(payload: ConnectionCreate) -> dict:
    if payload.type == ConnectionType.SSH:
        return {
            "password": payload.password,
            "private_key": payload.private_key,
            "private_key_passphrase": payload.private_key_passphrase,
        }
    if payload.type == ConnectionType.AWS:
        return {
            "aws_access_key_id": payload.aws_access_key_id,
            "aws_secret_access_key": payload.aws_secret_access_key,
            "aws_session_token": payload.aws_session_token,
        }
    if payload.type == ConnectionType.KUBERNETES:
        return {"kubeconfig": payload.kubeconfig}
    return {}


def create_connection(db: Session, payload: ConnectionCreate) -> Connection:
    secret_json = json.dumps(_secret_payload(payload))
    conn = Connection(
        name=payload.name,
        type=payload.type,
        config=payload.config or {},
        encrypted_credential=encrypt_secret(secret_json) if secret_json != "{}" else "",
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def get_decrypted_credential(conn: Connection) -> dict:
    if not conn.encrypted_credential:
        return {}
    return json.loads(decrypt_secret(conn.encrypted_credential))


def resolve_ssh_spec(conn: Connection, hostname: str, port: int, username: str) -> SSHConnectionSpec:
    creds = get_decrypted_credential(conn)
    return SSHConnectionSpec(
        hostname=hostname,
        port=port,
        username=username,
        password=creds.get("password") or None,
        private_key=creds.get("private_key") or None,
        private_key_passphrase=creds.get("private_key_passphrase") or None,
    )


def resolve_aws_credentials(conn: Connection) -> dict:
    creds = get_decrypted_credential(conn)
    region = (conn.config or {}).get("region", "us-east-1")
    return {
        "aws_access_key_id": creds.get("aws_access_key_id") or None,
        "aws_secret_access_key": creds.get("aws_secret_access_key") or None,
        "aws_session_token": creds.get("aws_session_token") or None,
        "region_name": region,
    }


def test_connection(db: Session, conn: Connection) -> ConnectionTestResult:
    result: ConnectionTestResult
    if conn.type == ConnectionType.SSH:
        cfg = conn.config or {}
        spec = resolve_ssh_spec(conn, cfg.get("hostname", ""), int(cfg.get("port", 22)), cfg.get("username", ""))
        try:
            tool = SSHTool(spec)
            tool.connect()
            out = tool.run("echo ok", timeout=10)
            tool.close()
            result = ConnectionTestResult(success=out.success, message="SSH connection succeeded" if out.success else "Command failed", details={"stdout": out.stdout})
        except Exception as exc:  # noqa: BLE001
            result = ConnectionTestResult(success=False, message=f"SSH connection failed: {exc}")
    elif conn.type == ConnectionType.AWS:
        from app.tools.aws_tool import AWSTool

        try:
            tool = AWSTool(resolve_aws_credentials(conn))
            identity = tool.get_caller_identity()
            conn.account_info = identity
            result = ConnectionTestResult(success=True, message="AWS credentials valid", details=identity)
        except Exception as exc:  # noqa: BLE001
            result = ConnectionTestResult(success=False, message=f"AWS validation failed: {exc}")
    else:
        result = ConnectionTestResult(success=False, message=f"Testing not implemented for {conn.type.value} yet")

    conn.status = ConnectionStatus.VALID if result.success else ConnectionStatus.INVALID
    conn.last_tested_at = datetime.now(timezone.utc)
    conn.last_test_message = result.message
    db.add(conn)
    db.commit()
    return result
