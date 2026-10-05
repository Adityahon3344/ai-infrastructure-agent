"""
Real Ansible integration. Each compiled step is a tiny, single-task playbook
(see compiler.py) written to a temp file and run with `ansible-playbook`
against a generated inventory pointing at exactly one target host, using the
resolved SSH credentials for that connection. Per-task execution means the
executor can stream progress and apply verification/risk logic per-task.

If ansible-playbook is not installed/available on PATH, this degrades
gracefully: it reports a clear, honest error (not a fake success) so the job
is marked FAILED with an actionable message rather than silently pretending
to succeed.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.connections.models import Connection
from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("tools.ansible")


class AnsibleNotAvailable(Exception):
    pass


def is_ansible_available() -> bool:
    return shutil.which(settings.ansible_playbook_binary) is not None


def _write_inventory(workdir: Path, hostname: str, port: int, username: str, private_key_path: str | None, password: str | None) -> Path:
    # IMPORTANT: connection variables (ansible_ssh_private_key_file, ansible_ssh_pass,
    # ansible_ssh_common_args, etc.) must live in a `[target:vars]` section, NOT as
    # bare lines under `[target]` — lines directly under a group header in INI
    # inventory syntax are parsed as additional HOSTS, not variables. Putting them
    # there silently creates bogus extra hosts and the real connection vars are
    # never applied (this previously caused every Ansible-based action to fail
    # with a misleading "Permission denied" even when the exact same credentials
    # worked fine for plain SSH/SFTP).
    lines = [
        "[target]",
        f"target ansible_host={hostname} ansible_port={port} ansible_user={username} ansible_connection=ssh",
        "",
        "[target:vars]",
        "ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'",
    ]
    if private_key_path:
        lines.append(f"ansible_ssh_private_key_file={private_key_path}")
    if password:
        lines.append(f"ansible_ssh_pass={password}")
        lines.append(f"ansible_become_pass={password}")
    inv_path = workdir / "inventory.ini"
    inv_path.write_text("\n".join(lines))
    return inv_path


def run_playbook_step(
    playbook_yaml: str,
    *,
    hostname: str,
    port: int,
    username: str,
    password: str | None = None,
    private_key: str | None = None,
    on_output=None,
    timeout: int | None = None,
) -> dict:
    """Runs one compiled Ansible task. Returns {success, stdout, stderr, changed}.
    `on_output(stream, line)` is called live for streaming to the frontend."""
    if not is_ansible_available():
        raise AnsibleNotAvailable(
            f"'{settings.ansible_playbook_binary}' was not found on PATH. Install Ansible on the control "
            "node to enable this feature (see README.md -> Ansible setup)."
        )

    timeout = timeout or settings.command_timeout_seconds
    with tempfile.TemporaryDirectory(dir=settings.ansible_workdir) as tmp:
        workdir = Path(tmp)
        playbook_path = workdir / "task.yml"
        playbook_path.write_text(playbook_yaml)

        key_path = None
        if private_key:
            key_path = workdir / "id_key"
            key_path.write_text(private_key)
            key_path.chmod(0o600)

        inventory = _write_inventory(workdir, hostname, port, username, str(key_path) if key_path else None, password)

        cmd = [settings.ansible_playbook_binary, "-i", str(inventory), str(playbook_path)]
        logger.info(f"Running ansible-playbook against {hostname}")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        output_lines: list[str] = []
        try:
            for line in process.stdout:  # type: ignore[union-attr]
                output_lines.append(line.rstrip("\n"))
                if on_output:
                    on_output("stdout", line.rstrip("\n"))
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            return {"success": False, "stdout": "\n".join(output_lines), "stderr": "Ansible run timed out", "changed": False}

        full_output = "\n".join(output_lines)
        return {
            "success": process.returncode == 0,
            "stdout": full_output,
            "stderr": "" if process.returncode == 0 else full_output,
            "changed": "changed=1" in full_output or "\"changed\": true" in full_output,
        }
