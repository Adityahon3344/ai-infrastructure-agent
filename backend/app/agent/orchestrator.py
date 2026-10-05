"""
The Agent Orchestrator implements the full pipeline described in the product
spec:

  USER PROMPT -> CHAT MEMORY/CONTEXT -> INTENT+REQUIREMENT ANALYSIS ->
  TARGET RESOLUTION -> ASK FOR MISSING INFO -> PLAN GENERATION -> VALIDATION ->
  RISK CHECK -> APPROVAL IF REQUIRED -> TOOL ROUTING -> EXECUTION ->
  LIVE STREAMING -> VERIFICATION -> RESULT -> MEMORY + JOB HISTORY

It never assumes information it doesn't have: if zero servers match, it offers
"Add a server"; if credentials are missing, it offers "Add connection"; if the
request is ambiguous it asks a concise clarifying question instead of guessing.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.agent.nlu import IntentResult, parse_intent
from app.approval.service import create_approval_request
from app.audit.service import record_audit_event
from app.catalog.catalog import RiskLevel
from app.connections.models import Connection, ConnectionType
from app.core.database import SessionLocal
from app.jobs.models import Job, JobStatus
from app.memory.models import MemoryScope
from app.memory.service import get_memory, set_memory
from app.planner.planspec import PlanSpec, PlanStep, PlanTarget
from app.risk.classifier import assess_plan
from app.servers.models import Server
from app.servers.tag_resolver import parse_target_phrase, resolve_servers
from app.validation.validator import validate_plan


@dataclass
class AgentResponse:
    message: str
    needs_server_selection: bool = False
    server_options: list[dict] = field(default_factory=list)
    needs_connection: bool = False
    needs_clarification: bool = False
    plan_preview: Optional[dict] = None
    job_id: Optional[str] = None
    approval: Optional[dict] = None
    risk_level: Optional[str] = None


_OS_KEYWORDS = ["ubuntu", "debian", "centos", "rhel", "redhat", "fedora", "amazon linux", "amazonlinux"]


def _resolve_target_servers(db: Session, intent: IntentResult, user_id: str | None, conversation_id: str | None) -> tuple[list[Server], str | None]:
    """Returns (servers, clarification_message). If clarification_message is
    set, the caller should ask the user that question instead of proceeding."""
    phrase = intent.target_phrase

    os_filter = None
    if phrase:
        for kw in _OS_KEYWORDS:
            if kw in phrase.lower():
                os_filter = kw.replace(" ", "").replace("amazonlinux", "amazon linux")
                phrase = phrase.lower().replace(kw, "").strip() or None
                break

    if phrase:
        parsed = parse_target_phrase(phrase)
        servers = resolve_servers(db, server_names=parsed.get("server_names"), environment=parsed.get("environment"), tags=parsed.get("tags") or None)
    else:
        remembered = get_memory(db, user_id=user_id, conversation_id=conversation_id, key="current_server_id")
        if remembered:
            remembered_server = db.get(Server, remembered)
            servers = [remembered_server] if remembered_server else []
        else:
            servers = db.query(Server).all()

    if os_filter:
        servers = [s for s in servers if os_filter in (s.os_distribution or "").lower()]

    if not servers:
        return [], None  # caller decides: offer "Add a server"

    # True ambiguity only when the user gave NO target phrase at all (so we
    # can't tell which server(s) they mean) and nothing is remembered from
    # this conversation. If they gave an explicit phrase (a name, "all X",
    # or an environment/role filter), multiple results are an intentional
    # multi-server operation, not ambiguity.
    if phrase is None and len(servers) > 1:
        if not get_memory(db, user_id=user_id, conversation_id=conversation_id, key="current_server_id"):
            return servers, "AMBIGUOUS"

    return servers, None


def _install_plan(intent: IntentResult, servers: list[Server]) -> PlanSpec:
    pkg = intent.package_name
    service_guess = {"nginx": "nginx", "apache2": "apache2", "docker": "docker", "mysql-server": "mysql",
                      "postgresql": "postgresql", "redis-server": "redis-server"}.get(pkg)
    steps = [
        PlanStep(action="package", description=f"Install package '{pkg}'", params={"name": pkg, "state": "present"}),
    ]
    expected = [f"Package '{pkg}' will be installed"]
    if service_guess:
        steps.append(PlanStep(action="systemd", description=f"Start and enable '{service_guess}'",
                               params={"name": service_guess, "state": "started", "enabled": True},
                               verify="service_active"))
        expected.append(f"Service '{service_guess}' will be started and enabled on boot")
    return PlanSpec(
        summary=f"Install {pkg} on {len(servers)} server(s), then start and enable the service if applicable",
        intent="install_package",
        target=PlanTarget(kind="servers", server_ids=[s.id for s in servers]),
        steps=steps,
        expected_changes=expected,
        no_changes_note="No existing files will be deleted.",
    )


def _service_plan(intent: IntentResult, servers: list[Server]) -> PlanSpec:
    action = intent.service_action or "restarted"
    steps = [PlanStep(action="systemd", description=f"Set '{intent.service_name}' to {action}",
                       params={"name": intent.service_name, "state": action}, verify="service_active")]
    return PlanSpec(
        summary=f"{action.capitalize()} service '{intent.service_name}' on {len(servers)} server(s)",
        intent="manage_service",
        target=PlanTarget(kind="servers", server_ids=[s.id for s in servers]),
        steps=steps,
        expected_changes=[f"Service '{intent.service_name}' will be {action}"],
    )


def _create_path_plan(intent: IntentResult, servers: list[Server]) -> PlanSpec:
    steps = [PlanStep(action="file", description=f"Create directory '{intent.path}'", params={"path": intent.path, "state": "directory", "mode": "0755"}, verify="path_exists")]
    return PlanSpec(
        summary=f"Create directory {intent.path} on {len(servers)} server(s)",
        intent="create_path",
        target=PlanTarget(kind="servers", server_ids=[s.id for s in servers]),
        steps=steps,
        expected_changes=[f"Directory '{intent.path}' will be created if missing"],
        no_changes_note="No existing files will be deleted or modified.",
        requires_confirmation=False,
    )


def _deploy_plan(intent: IntentResult, servers: list[Server]) -> PlanSpec:
    path = intent.path or "/opt/app"
    steps = [PlanStep(action="file", description=f"Ensure deploy directory '{path}' exists", params={"path": path, "state": "directory", "mode": "0755"})]
    if intent.repo_url:
        steps.append(PlanStep(action="git", description=f"Clone/update repository into {path}", params={"repo": intent.repo_url, "dest": path}))
    return PlanSpec(
        summary=f"Deploy application to {path} on {len(servers)} server(s)",
        intent="deploy",
        target=PlanTarget(kind="servers", server_ids=[s.id for s in servers]),
        steps=steps,
        expected_changes=[f"Application files will be placed under {path}"],
    )


def _inspect_plan(intent: IntentResult, servers: list[Server]) -> PlanSpec:
    action_map = {"disk": "check_disk_usage", "cpu": "check_cpu_ram", "ram": "check_cpu_ram", "facts": "gather_facts"}
    if intent.inspect_kind == "service_status" and intent.service_name:
        steps = [PlanStep(action="check_service_status", description=f"Check status of '{intent.service_name}'", params={"service_name": intent.service_name})]
    else:
        action = action_map.get(intent.inspect_kind or "facts", "gather_facts")
        steps = [PlanStep(action=action, description=f"Inspect {intent.inspect_kind or 'system facts'}", params={})]
    return PlanSpec(
        summary=f"Read-only inspection ({intent.inspect_kind or 'facts'}) on {len(servers)} server(s)",
        intent="inspect",
        target=PlanTarget(kind="servers", server_ids=[s.id for s in servers]),
        steps=steps,
        expected_changes=["No changes — this is a read-only inspection."],
        requires_confirmation=False,
    )


def build_plan(intent: IntentResult, servers: list[Server]) -> PlanSpec:
    builders = {
        "install_package": _install_plan,
        "manage_service": _service_plan,
        "create_path": _create_path_plan,
        "deploy": _deploy_plan,
        "inspect": _inspect_plan,
    }
    builder = builders.get(intent.intent)
    if not builder:
        raise ValueError(f"No plan builder registered for intent '{intent.intent}'")
    return builder(intent, servers)


def _server_options(servers: list[Server]) -> list[dict]:
    return [{"id": s.id, "name": s.name, "hostname": s.hostname, "environment": s.environment, "os": s.os_distribution} for s in servers]


def handle_message(db: Session, *, user_id: str | None, conversation_id: str, text: str, selected_server_ids: list[str] | None = None) -> AgentResponse:
    intent = parse_intent(text)

    if intent.intent == "unknown":
        return AgentResponse(
            message="I'm not sure what infrastructure action you want. Try things like \"install nginx on web-01\", "
                    "\"check disk usage on all production servers\", or \"create an EC2 instance\".",
            needs_clarification=True,
        )

    if intent.intent == "list_servers":
        servers = db.query(Server).all()
        if not servers:
            return AgentResponse(message="You don't have any servers registered yet.", needs_server_selection=False, server_options=[])
        lines = "\n".join(f"- {s.name} ({s.hostname}) — {s.environment}, {s.os_distribution or 'OS unknown'}, {s.status.value}" for s in servers)
        return AgentResponse(message=f"You have {len(servers)} server(s):\n{lines}")

    if intent.intent in ("provision_ec2", "provision_vpc", "list_aws_resource"):
        conn = db.query(Connection).filter(Connection.type == ConnectionType.AWS, Connection.disabled == False).first()  # noqa: E712
        if not conn:
            return AgentResponse(message="This requires an AWS connection and none is configured yet.", needs_connection=True)
        return AgentResponse(
            message="AWS actions are available via POST /api/aws/* endpoints (dynamic discovery + provisioning). "
                    "Use the Servers/Connections UI or ask me to 'show available EC2 instance types' for a live discovery example.",
        )

    if "package_name" in (intent.missing_info or []):
        return AgentResponse(message="Which package would you like me to install? (e.g. nginx, docker, python3.12)", needs_clarification=True)
    if "service_name" in (intent.missing_info or []):
        return AgentResponse(message="Which service should I act on?", needs_clarification=True)
    if "path" in (intent.missing_info or []):
        return AgentResponse(message="What path or folder name should I create?", needs_clarification=True)

    if selected_server_ids:
        servers = db.query(Server).filter(Server.id.in_(selected_server_ids)).all()
    else:
        servers, clarification = _resolve_target_servers(db, intent, user_id, conversation_id)
        if clarification == "AMBIGUOUS":
            return AgentResponse(
                message="Multiple servers match — which one(s) should I target?",
                needs_server_selection=True, server_options=_server_options(servers),
            )

    if not servers:
        return AgentResponse(
            message="I couldn't find a matching server. Would you like to add one?",
            needs_server_selection=True, server_options=[],
        )

    missing_connection = [s for s in servers if not s.connection_id]
    if missing_connection:
        names = ", ".join(s.name for s in missing_connection)
        return AgentResponse(message=f"These servers have no connection configured yet: {names}. Please add a connection first.", needs_connection=True)

    try:
        plan = build_plan(intent, servers)
    except ValueError as exc:
        return AgentResponse(message=str(exc), needs_clarification=True)

    validation = validate_plan(plan)
    if not validation.valid:
        return AgentResponse(message="I generated a plan but it failed validation:\n" + "\n".join(validation.errors), needs_clarification=True)

    risk = assess_plan(plan)

    set_memory(db, user_id=user_id, conversation_id=conversation_id, scope=MemoryScope.SHORT_TERM, key="current_server_id", value=servers[0].id, source="chat")

    job = Job(
        conversation_id=conversation_id, user_id=user_id, prompt=text, plan=plan.model_dump(),
        risk_level=risk.level.value, risk_reasons=risk.reasons, target_server_ids=[s.id for s in servers],
        tools_used=list({_compiled_kind_for(step.action) for step in plan.steps}),
        status=JobStatus.PLANNING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    plan_preview = {
        "summary": plan.summary,
        "targets": _server_options(servers),
        "steps": [{"action": s.action, "description": s.description} for s in plan.steps],
        "expected_changes": plan.expected_changes,
        "no_changes_note": plan.no_changes_note,
        "risk_level": risk.level.value,
        "risk_reasons": risk.reasons,
        "job_id": job.id,
    }

    record_audit_event(user_id=user_id, action="plan_generated", resource=f"job:{job.id}", details=plan.summary)

    if risk.requires_approval:
        approval = create_approval_request(db, job, plan, risk, user_id)
        return AgentResponse(
            message=f"This action is {risk.level.value.upper()} risk and needs your approval before I proceed.",
            plan_preview=plan_preview, job_id=job.id, risk_level=risk.level.value,
            approval={"id": approval.id, "action_summary": approval.action_summary, "target_summary": approval.target_summary,
                      "expected_changes": approval.expected_changes, "risk_level": approval.risk_level, "impact": approval.impact},
        )

    from app.execution.executor import execute_job
    from app.chat.service import get_or_create_event_loop
    import threading

    loop = get_or_create_event_loop()
    threading.Thread(target=execute_job, args=(job.id, SessionLocal, loop), daemon=True).start()

    return AgentResponse(
        message=f"Running: {plan.summary}",
        plan_preview=plan_preview, job_id=job.id, risk_level=risk.level.value,
    )


def _compiled_kind_for(action: str) -> str:
    from app.compiler.compiler import ANSIBLE_ACTION_KEYS, _AWS_ACTION_KEYS, _DOCKER_ACTION_KEYS, _SSH_ACTION_KEYS
    if action in ANSIBLE_ACTION_KEYS:
        return "ansible"
    if action in _SSH_ACTION_KEYS:
        return "ssh"
    if action in _DOCKER_ACTION_KEYS:
        return "docker"
    if action in _AWS_ACTION_KEYS:
        return "aws"
    if action == "git_clone" or action == "git":
        return "git"
    return "unknown"
