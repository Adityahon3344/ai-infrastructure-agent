"""
Central application configuration.

Everything is driven by environment variables (see .env.example). Nothing here
imposes artificial limits on server counts, instance types, etc. — those are
resolved dynamically at runtime from the database / cloud provider APIs.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "dev-secret-key-change-me"
    database_url: str = f"sqlite:///{DATA_DIR}/agent.db"

    credential_encryption_key: str = ""

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    aws_allowed_regions: str = "us-east-1,us-east-2,us-west-1,us-west-2,eu-west-1"

    ansible_playbook_binary: str = "ansible-playbook"
    ansible_workdir: str = str(DATA_DIR / "ansible")

    ssh_connect_timeout_seconds: int = 15
    command_timeout_seconds: int = 300
    max_parallel_server_executions: int = 10

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def aws_allowed_region_list(self) -> List[str]:
        return [r.strip() for r in self.aws_allowed_regions.split(",") if r.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
Path(settings.ansible_workdir).mkdir(parents=True, exist_ok=True)
