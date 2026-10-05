"""
Failure classification + human-readable diagnosis + safe-fix suggestion.
Pattern-matches common, well-understood failure signatures (apt lock, DNS
resolution failure, permission denied, disk full, service unit not found,
connection refused/timeout) against captured stderr/stdout. Unknown failures
are surfaced honestly rather than guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Diagnosis:
    category: str
    human_explanation: str
    safe_fix_available: bool
    safe_fix_description: str = ""
    safe_fix_action: str | None = None  # catalog action key for the AI-proposed remediation, still subject to approval
    retryable: bool = False


_RULES: list[tuple[str, str, str, bool, str, str | None, bool]] = [
    ("Could not get lock", "package_manager_locked",
     "The package manager (apt/dnf/yum) is locked by another process — likely an unattended background update.",
     True, "Wait a short time for the other process to finish and retry.", None, True),
    ("Temporary failure in name resolution", "dns_failure",
     "The server could not resolve a hostname — DNS is unreachable or misconfigured on that host.",
     False, "", None, False),
    ("Permission denied", "permission_denied",
     "The command failed due to insufficient permissions. The connecting user may need sudo/root privileges for this action.",
     False, "", None, False),
    ("No space left on device", "disk_full",
     "The target filesystem is full, so the operation could not complete.",
     False, "", None, False),
    ("Service is in unknown state", "init_system_unavailable",
     "The target does not have a running init system (systemd) that Ansible can control — this is common "
     "inside minimal containers. Service management requires a normal server/VM with systemd running as PID 1.",
     False, "", None, False),
    ("Unit .* could not be found", "unit_not_found",
     "The requested systemd service does not exist on this host — it may not be installed yet.",
     True, "Install the corresponding package before starting/enabling the service.", "package", False),
    ("Connection refused", "connection_refused",
     "The SSH connection was refused — the SSH daemon may be down or a firewall is blocking the port.",
     False, "", None, False),
    ("Connection timed out", "connection_timeout",
     "The connection attempt timed out — the host may be unreachable, powered off, or behind a firewall.",
     False, "", None, False),
    ("command not found", "command_missing",
     "The command used by this step is not installed on the target host.",
     False, "", None, False),
]


def diagnose(stdout: str, stderr: str) -> Diagnosis:
    haystack = f"{stdout}\n{stderr}"
    import re
    for pattern, category, explanation, safe_fix, fix_desc, fix_action, retryable in _RULES:
        if re.search(pattern, haystack, re.IGNORECASE):
            return Diagnosis(category, explanation, safe_fix, fix_desc, fix_action, retryable)
    return Diagnosis(
        "unknown",
        "The action failed and the error did not match a known pattern. Manual investigation is recommended.",
        False,
    )
