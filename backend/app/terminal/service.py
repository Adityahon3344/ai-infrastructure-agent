"""
Controlled terminal: executes a single command per request (not a full
interactive PTY) over the server's existing SSH connection, respecting the
same audit/authorization/timeout/cancellation guarantees as every other
execution path. This is intentionally NOT unrestricted shell access — every
command is authenticated, authorized (server-level permission), logged to the
audit trail, and subject to COMMAND_TIMEOUT_SECONDS.
"""
from __future__ import annotations

import threading
import uuid

from app.audit.service import record_audit_event
from app.connections.models import Connection
from app.connections.service import resolve_ssh_spec
from app.servers.models import Server
from app.tools.ssh_tool import SSHTool

_active_sessions: dict[str, threading.Event] = {}

BLOCKED_PATTERNS = ["rm -rf /", ":(){ :|:& };:", "mkfs", "dd if=/dev/zero of=/dev/"]


def is_blocked(command: str) -> bool:
    return any(p in command for p in BLOCKED_PATTERNS)


def run_command(server: Server, connection: Connection, command: str, user_id: str | None, on_output, timeout: int = 60) -> dict:
    if is_blocked(command):
        record_audit_event(user_id=user_id, action="terminal_command_blocked", resource=f"server:{server.id}", details=command)
        return {"success": False, "error": "This command matches a blocked destructive pattern and was not executed."}

    session_id = str(uuid.uuid4())
    cancel_event = threading.Event()
    _active_sessions[session_id] = cancel_event

    record_audit_event(user_id=user_id, action="terminal_command_run", resource=f"server:{server.id}", details=command)
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        result = tool.run_streaming(command, on_output=on_output, timeout=timeout)
        return {"success": result.success, "exit_code": result.exit_code, "session_id": session_id, "timed_out": result.timed_out}
    finally:
        tool.close()
        _active_sessions.pop(session_id, None)


def cancel_session(session_id: str) -> bool:
    event = _active_sessions.get(session_id)
    if event:
        event.set()
        return True
    return False
