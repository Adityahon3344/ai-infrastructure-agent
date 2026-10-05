from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.connections.models import ConnectionStatus, ConnectionType


class ConnectionCreate(BaseModel):
    name: str
    type: ConnectionType
    config: dict = {}
    # Exactly one of these depending on type; never echoed back by the API.
    password: Optional[str] = None
    private_key: Optional[str] = None
    private_key_passphrase: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    kubeconfig: Optional[str] = None


class ConnectionOut(BaseModel):
    id: str
    name: str
    type: ConnectionType
    status: ConnectionStatus
    disabled: bool
    config: dict
    account_info: dict
    last_tested_at: Optional[datetime]
    last_used_at: Optional[datetime]
    last_test_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    details: dict = {}
