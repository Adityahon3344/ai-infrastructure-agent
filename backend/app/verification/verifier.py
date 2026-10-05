"""
Never assume success just because a command returned 0. After executing an
action, run an independent verification check appropriate to that action —
service state, port reachability, directory existence, HTTP health, etc.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.connections.service import resolve_ssh_spec
from app.servers.models import Server
from app.connections.models import Connection
from app.tools.ssh_tool import SSHTool


@dataclass
class VerificationResult:
    verified: bool
    message: str
    details: dict


def verify_service_active(server: Server, connection: Connection, service_name: str) -> VerificationResult:
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        result = tool.run(f"systemctl is-active {service_name}", timeout=15)
        active = result.stdout.strip() == "active"
        return VerificationResult(active, f"service '{service_name}' is {'active' if active else 'NOT active'}", {"stdout": result.stdout})
    finally:
        tool.close()


def verify_service_enabled(server: Server, connection: Connection, service_name: str) -> VerificationResult:
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        result = tool.run(f"systemctl is-enabled {service_name}", timeout=15)
        enabled = result.stdout.strip() in ("enabled", "static")
        return VerificationResult(enabled, f"service '{service_name}' is {'enabled' if enabled else 'NOT enabled'} on boot", {"stdout": result.stdout})
    finally:
        tool.close()


def verify_path_exists(server: Server, connection: Connection, path: str) -> VerificationResult:
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        result = tool.run(f"test -e '{path}' && echo EXISTS || echo MISSING", timeout=15)
        exists = "EXISTS" in result.stdout
        return VerificationResult(exists, f"path '{path}' {'exists' if exists else 'does NOT exist'}", {})
    finally:
        tool.close()


def verify_port_listening(server: Server, connection: Connection, port: int) -> VerificationResult:
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        result = tool.run(f"(ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep -q ':{port} ' && echo LISTENING || echo CLOSED", timeout=15)
        listening = "LISTENING" in result.stdout
        return VerificationResult(listening, f"port {port} is {'listening' if listening else 'NOT listening'}", {})
    finally:
        tool.close()


def verify_http_health(server: Server, connection: Connection, path: str = "/", port: int = 80) -> VerificationResult:
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}{path} || echo 000"
        result = tool.run(cmd, timeout=15)
        code = result.stdout.strip()
        healthy = code.startswith("2") or code.startswith("3")
        return VerificationResult(healthy, f"HTTP health check returned {code}", {"http_code": code})
    finally:
        tool.close()


# Maps a catalog action to the verification(s) it should trigger, keyed by
# service/path parameters present on the step.
def verify_step(action: str, params: dict, server: Server, connection: Connection) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    if action in ("service", "systemd") and params.get("name"):
        if params.get("state") in ("started", "restarted", None):
            results.append(verify_service_active(server, connection, params["name"]))
        if params.get("enabled"):
            results.append(verify_service_enabled(server, connection, params["name"]))
    if action == "file" and params.get("state") == "directory" and params.get("path"):
        results.append(verify_path_exists(server, connection, params["path"]))
    if action in ("package", "apt", "dnf", "yum") and params.get("name") in ("nginx", "apache2", "httpd"):
        svc = "apache2" if params["name"] == "apache2" else ("httpd" if params["name"] == "httpd" else "nginx")
        results.append(verify_service_active(server, connection, svc))
        results.append(verify_port_listening(server, connection, 80))
    return results
