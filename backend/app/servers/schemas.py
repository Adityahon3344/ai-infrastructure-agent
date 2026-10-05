from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.servers.models import ServerStatus


class ServerCreate(BaseModel):
    name: str
    hostname: str
    ip_address: str = ""
    port: int = 22
    username: str = ""
    environment: str = "production"
    tags: dict[str, str] = Field(default_factory=dict)
    connection_id: Optional[str] = None
    notes: str = ""


class ServerUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    environment: Optional[str] = None
    tags: Optional[dict[str, str]] = None
    connection_id: Optional[str] = None
    notes: Optional[str] = None


class ServerOut(BaseModel):
    id: str
    name: str
    hostname: str
    ip_address: str
    port: int
    username: str
    os_family: str
    os_distribution: str
    os_version: str
    architecture: str
    environment: str
    tags: dict
    connection_id: Optional[str]
    status: ServerStatus
    last_seen: Optional[datetime]
    cpu_cores: Optional[int]
    ram_mb: Optional[int]
    disk_gb: Optional[float]
    capabilities: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
