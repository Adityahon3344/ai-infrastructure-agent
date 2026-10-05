"""
The Catalog is the single source of truth for "what the AI is allowed to
propose". It lists every Ansible module, AWS action, and generic tool action
the system knows how to execute safely, along with its default risk level and
parameter schema. The Validator (app/validation) rejects anything not in here.

This is what makes the architecture safe: "The AI proposes; only reviewed/
validated code executes." The AI never gets to run arbitrary shell/API code —
it can only select from this catalog and fill in parameters, which are then
validated before compilation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class CatalogEntry:
    id: str                      # e.g. "ansible.package", "aws.ec2.run_instances"
    category: str                # ansible | aws | ssh | docker | git | monitoring | kubernetes
    description: str
    risk: RiskLevel
    required_params: list[str] = field(default_factory=list)
    optional_params: list[str] = field(default_factory=list)
    reversible: bool = True


# ---------------------------------------------------------------------------
# Ansible modules allowlist (dynamic task composition draws only from this set)
# ---------------------------------------------------------------------------
ANSIBLE_MODULES: dict[str, CatalogEntry] = {
    "package": CatalogEntry("ansible.package", "ansible", "Install/remove a package using the OS-native package manager", RiskLevel.MEDIUM, ["name", "state"]),
    "apt": CatalogEntry("ansible.apt", "ansible", "Debian/Ubuntu package management", RiskLevel.MEDIUM, ["name", "state"], ["update_cache"]),
    "dnf": CatalogEntry("ansible.dnf", "ansible", "Fedora/RHEL8+ package management", RiskLevel.MEDIUM, ["name", "state"]),
    "yum": CatalogEntry("ansible.yum", "ansible", "RHEL/CentOS package management", RiskLevel.MEDIUM, ["name", "state"]),
    "service": CatalogEntry("ansible.service", "ansible", "Start/stop/enable a service", RiskLevel.MEDIUM, ["name", "state"], ["enabled"]),
    "systemd": CatalogEntry("ansible.systemd", "ansible", "Manage a systemd unit", RiskLevel.MEDIUM, ["name", "state"], ["enabled", "daemon_reload"]),
    "file": CatalogEntry("ansible.file", "ansible", "Create/remove files, directories, symlinks; set permissions", RiskLevel.MEDIUM, ["path", "state"], ["mode", "owner", "group"]),
    "copy": CatalogEntry("ansible.copy", "ansible", "Copy content/file to a remote path", RiskLevel.MEDIUM, ["dest"], ["content", "src", "mode", "backup"]),
    "template": CatalogEntry("ansible.template", "ansible", "Render and copy a Jinja2 template", RiskLevel.MEDIUM, ["dest", "content"], ["mode", "backup"]),
    "user": CatalogEntry("ansible.user", "ansible", "Manage a user account", RiskLevel.HIGH, ["name", "state"], ["groups", "shell"], reversible=False),
    "group": CatalogEntry("ansible.group", "ansible", "Manage a group", RiskLevel.MEDIUM, ["name", "state"]),
    "command": CatalogEntry("ansible.command", "ansible", "Run a single allowlisted command (no shell features)", RiskLevel.MEDIUM, ["cmd"], ["chdir"]),
    "shell": CatalogEntry("ansible.shell", "ansible", "Run a shell command (pipes/redirection) — requires stricter review", RiskLevel.HIGH, ["cmd"], ["chdir"], reversible=False),
    "git": CatalogEntry("ansible.git", "ansible", "Clone/update a git repository", RiskLevel.MEDIUM, ["repo", "dest"], ["version"]),
    "unarchive": CatalogEntry("ansible.unarchive", "ansible", "Extract an archive on the remote host", RiskLevel.MEDIUM, ["src", "dest"], ["remote_src"]),
    "cron": CatalogEntry("ansible.cron", "ansible", "Manage a cron job", RiskLevel.MEDIUM, ["name", "job"], ["minute", "hour", "state"]),
    "mount": CatalogEntry("ansible.mount", "ansible", "Manage a filesystem mount", RiskLevel.HIGH, ["path", "src", "fstype", "state"], reversible=False),
    "lineinfile": CatalogEntry("ansible.lineinfile", "ansible", "Ensure a line is present/absent in a file", RiskLevel.MEDIUM, ["path", "line"], ["state", "regexp", "backup"]),
    "replace": CatalogEntry("ansible.replace", "ansible", "Regex replace text in a file", RiskLevel.MEDIUM, ["path", "regexp", "replace"], ["backup"]),
    "setup": CatalogEntry("ansible.setup", "ansible", "Gather Ansible facts (read-only)", RiskLevel.LOW, []),
}

# Modules that require explicit review by policy even though individually
# "medium" — combined with destructive states they escalate (see risk engine).
DESTRUCTIVE_STATE_VALUES = {"absent", "removed"}

# ---------------------------------------------------------------------------
# AWS actions allowlist
# ---------------------------------------------------------------------------
AWS_ACTIONS: dict[str, CatalogEntry] = {
    "list_regions": CatalogEntry("aws.ec2.list_regions", "aws", "List available AWS regions", RiskLevel.LOW, []),
    "list_instance_types": CatalogEntry("aws.ec2.list_instance_types", "aws", "Dynamically discover EC2 instance types", RiskLevel.LOW, []),
    "list_amis": CatalogEntry("aws.ec2.list_amis", "aws", "List AMIs", RiskLevel.LOW, []),
    "list_vpcs": CatalogEntry("aws.ec2.list_vpcs", "aws", "List VPCs", RiskLevel.LOW, []),
    "list_subnets": CatalogEntry("aws.ec2.list_subnets", "aws", "List subnets", RiskLevel.LOW, []),
    "list_security_groups": CatalogEntry("aws.ec2.list_security_groups", "aws", "List security groups", RiskLevel.LOW, []),
    "list_instances": CatalogEntry("aws.ec2.list_instances", "aws", "List EC2 instances", RiskLevel.LOW, []),
    "list_s3_buckets": CatalogEntry("aws.s3.list_buckets", "aws", "List S3 buckets", RiskLevel.LOW, []),
    "list_rds_instances": CatalogEntry("aws.rds.list_instances", "aws", "List RDS instances", RiskLevel.LOW, []),
    "run_instances": CatalogEntry("aws.ec2.run_instances", "aws", "Launch new EC2 instance(s)", RiskLevel.MEDIUM, ["image_id", "instance_type"], ["key_name", "subnet_id", "security_group_ids", "tags"]),
    "terminate_instances": CatalogEntry("aws.ec2.terminate_instances", "aws", "Terminate EC2 instance(s) — irreversible", RiskLevel.HIGH, ["instance_ids"], reversible=False),
    "create_vpc": CatalogEntry("aws.ec2.create_vpc", "aws", "Create a new VPC", RiskLevel.MEDIUM, ["cidr_block"], ["tags"]),
}

# ---------------------------------------------------------------------------
# Generic / cross-cutting actions (SSH-level, Docker, Git, monitoring)
# ---------------------------------------------------------------------------
GENERIC_ACTIONS: dict[str, CatalogEntry] = {
    "gather_facts": CatalogEntry("ssh.gather_facts", "ssh", "Collect OS/CPU/RAM/disk facts (read-only)", RiskLevel.LOW, []),
    "check_service_status": CatalogEntry("ssh.check_service_status", "ssh", "Check whether a service is active (read-only)", RiskLevel.LOW, ["service_name"]),
    "check_disk_usage": CatalogEntry("ssh.check_disk_usage", "ssh", "Report disk usage (read-only)", RiskLevel.LOW, []),
    "check_cpu_ram": CatalogEntry("ssh.check_cpu_ram", "ssh", "Report CPU/RAM usage (read-only)", RiskLevel.LOW, []),
    "docker_ps": CatalogEntry("docker.ps", "docker", "List Docker containers (read-only)", RiskLevel.LOW, []),
    "docker_run": CatalogEntry("docker.run", "docker", "Run a Docker container", RiskLevel.MEDIUM, ["image"], ["name", "ports", "env", "volumes"]),
    "docker_stop": CatalogEntry("docker.stop", "docker", "Stop a Docker container", RiskLevel.MEDIUM, ["name"]),
    "docker_remove": CatalogEntry("docker.remove", "docker", "Remove a Docker container", RiskLevel.HIGH, ["name"], reversible=False),
    "git_clone": CatalogEntry("git.clone", "git", "Clone a repository to the remote host", RiskLevel.MEDIUM, ["repo", "dest"]),
    "k8s_list_pods": CatalogEntry("kubernetes.list_pods", "kubernetes", "List pods (read-only)", RiskLevel.LOW, ["namespace"]),
    "k8s_apply": CatalogEntry("kubernetes.apply", "kubernetes", "Apply a Kubernetes manifest", RiskLevel.HIGH, ["manifest"]),
}

FULL_CATALOG: dict[str, CatalogEntry] = {**ANSIBLE_MODULES, **AWS_ACTIONS, **GENERIC_ACTIONS}


def get_entry(action_key: str) -> CatalogEntry | None:
    return FULL_CATALOG.get(action_key)


def list_catalog() -> list[dict]:
    return [
        {
            "key": key,
            "id": entry.id,
            "category": entry.category,
            "description": entry.description,
            "risk": entry.risk.value,
            "required_params": entry.required_params,
            "optional_params": entry.optional_params,
            "reversible": entry.reversible,
        }
        for key, entry in FULL_CATALOG.items()
    ]
