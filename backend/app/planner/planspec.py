"""
PlanSpec: the structured, machine-checkable representation of "what the agent
intends to do". The LLM (or the rule-based NLU fallback) never emits raw shell
commands or boto3 calls — it emits a PlanSpec, which is then validated against
the Catalog, risk-classified, optionally approved, compiled into concrete
Ansible tasks / boto3 calls, and only THEN executed.

    Natural Language -> PlanSpec -> Catalog validation -> Compilation -> Execution
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """One catalog action with concrete parameters, targeted at one or more
    servers (for ssh/ansible/docker/git steps) or a cloud connection (for aws/kubernetes steps)."""

    action: str  # must exist in app.catalog.catalog.FULL_CATALOG
    description: str
    params: dict[str, Any] = Field(default_factory=dict)
    verify: Optional[str] = None  # verification action key, if any


class PlanTarget(BaseModel):
    kind: Literal["servers", "aws_connection", "kubernetes_connection"]
    server_ids: list[str] = Field(default_factory=list)
    connection_id: Optional[str] = None


class PlanSpec(BaseModel):
    """The full structured plan produced for one user request."""

    summary: str
    intent: str  # e.g. "install_package", "restart_service", "provision_ec2", "inspect"
    target: PlanTarget
    steps: list[PlanStep]
    expected_changes: list[str] = Field(default_factory=list)
    no_changes_note: Optional[str] = None  # e.g. "No files will be deleted."
    requires_confirmation: bool = True

    def step_actions(self) -> list[str]:
        return [s.action for s in self.steps]
