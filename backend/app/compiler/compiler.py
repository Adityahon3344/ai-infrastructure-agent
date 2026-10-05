"""
Compiles a VALIDATED PlanSpec into concrete, executable artifacts:
  - Ansible steps  -> a real Ansible playbook (YAML) using only allowlisted modules
  - AWS steps      -> ordered boto3 calls via AWSTool
  - ssh/docker/git -> ordered shell command sequences run over SSH

The compiler NEVER accepts unvalidated input — callers must run
app.validation.validator.validate_plan() first and check `.valid`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from app.catalog.catalog import get_entry
from app.planner.planspec import PlanSpec, PlanStep


@dataclass
class CompiledTask:
    step_index: int
    action: str
    description: str
    kind: str  # ansible | aws | ssh | docker | git | kubernetes
    payload: Any  # ansible: playbook YAML str; aws: dict(action,kwargs); ssh: shell command str; etc.
    verify: str | None = None


@dataclass
class CompiledPlan:
    tasks: list[CompiledTask] = field(default_factory=list)


ANSIBLE_ACTION_KEYS = {"package", "apt", "dnf", "yum", "service", "systemd", "file", "copy", "template",
                       "user", "group", "command", "shell", "git", "unarchive", "cron", "mount",
                       "lineinfile", "replace", "setup"}

# Ansible actions that need root privileges on a real server. In practice this
# is "every state-changing module" — installing packages, managing services,
# writing files/directories (commonly under root-owned paths like /opt, /etc,
# /var), managing users/mounts/cron, running arbitrary commands. The only
# genuine exception is `setup` (fact-gathering), which is read-only and never
# needs elevation. Without this, almost any real deployment (where the SSH
# user isn't literally `root`) fails with "Permission denied" on step 1.
_PRIVILEGED_ACTIONS = ANSIBLE_ACTION_KEYS - {"setup"}

_SSH_ACTION_KEYS = {"gather_facts", "check_service_status", "check_disk_usage", "check_cpu_ram"}
_DOCKER_ACTION_KEYS = {"docker_ps", "docker_run", "docker_stop", "docker_remove"}
_AWS_ACTION_KEYS = {"list_regions", "list_instance_types", "list_amis", "list_vpcs", "list_subnets",
                    "list_security_groups", "list_instances", "list_s3_buckets", "list_rds_instances",
                    "run_instances", "terminate_instances", "create_vpc"}
_K8S_ACTION_KEYS = {"k8s_list_pods", "k8s_apply"}


def _compile_ansible_step(step: PlanStep) -> str:
    """Builds a single-play, single-task Ansible playbook YAML string. Each step
    is compiled independently so the executor can stream per-task progress and
    the approval/verification layers stay simple and auditable."""
    module = step.action
    play = [{
        "name": step.description,
        "hosts": "target",
        "gather_facts": module == "setup",
        "become": module in _PRIVILEGED_ACTIONS,
        "become_method": "sudo",
        "tasks": [{"name": step.description, module: step.params}],
    }]
    return yaml.safe_dump(play, sort_keys=False)


def _compile_ssh_step(step: PlanStep) -> str:
    mapping = {
        "gather_facts": "uname -a && cat /etc/os-release",
        "check_disk_usage": "df -h",
        "check_cpu_ram": "top -bn1 | head -5 && free -h",
        "check_service_status": "systemctl is-active {service_name} || service {service_name} status",
    }
    template = mapping[step.action]
    return template.format(**step.params)


def _compile_docker_step(step: PlanStep) -> str:
    if step.action == "docker_ps":
        return "docker ps -a"
    if step.action == "docker_run":
        p = step.params
        cmd = ["docker", "run", "-d"]
        if p.get("name"):
            cmd += ["--name", p["name"]]
        for port in p.get("ports", []) or []:
            cmd += ["-p", str(port)]
        for env_kv in p.get("env", []) or []:
            cmd += ["-e", str(env_kv)]
        for vol in p.get("volumes", []) or []:
            cmd += ["-v", str(vol)]
        cmd.append(p["image"])
        return " ".join(cmd)
    if step.action == "docker_stop":
        return f"docker stop {step.params['name']}"
    if step.action == "docker_remove":
        return f"docker rm -f {step.params['name']}"
    raise ValueError(f"Unknown docker action {step.action}")


def compile_plan(plan: PlanSpec) -> CompiledPlan:
    compiled = CompiledPlan()
    for i, step in enumerate(plan.steps):
        entry = get_entry(step.action)
        if entry is None:
            raise ValueError(f"Cannot compile unknown action '{step.action}' — validate_plan() should have caught this")

        if step.action in ANSIBLE_ACTION_KEYS:
            compiled.tasks.append(CompiledTask(i, step.action, step.description, "ansible", _compile_ansible_step(step), step.verify))
        elif step.action in _SSH_ACTION_KEYS:
            compiled.tasks.append(CompiledTask(i, step.action, step.description, "ssh", _compile_ssh_step(step), step.verify))
        elif step.action in _DOCKER_ACTION_KEYS:
            compiled.tasks.append(CompiledTask(i, step.action, step.description, "docker", _compile_docker_step(step), step.verify))
        elif step.action in _AWS_ACTION_KEYS:
            compiled.tasks.append(CompiledTask(i, step.action, step.description, "aws", {"action": step.action, "params": step.params}, step.verify))
        elif step.action in _K8S_ACTION_KEYS:
            compiled.tasks.append(CompiledTask(i, step.action, step.description, "kubernetes", {"action": step.action, "params": step.params}, step.verify))
        elif step.action == "git_clone":
            compiled.tasks.append(CompiledTask(i, step.action, step.description, "git", f"git clone {step.params['repo']} {step.params['dest']}", step.verify))
        else:
            raise ValueError(f"No compiler rule for action '{step.action}'")
    return compiled
