"""
Tool Router: given a CompiledTask (kind + payload) and its resolved target
(server + connection, or cloud connection), picks the correct underlying
integration to execute it. This is the seam that makes the agent extensible —
new tools (Azure, GCP, more k8s ops, etc.) register here without touching the
planner, validator, risk engine, or executor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.compiler.compiler import CompiledTask
from app.connections.models import Connection
from app.connections.service import resolve_aws_credentials, resolve_ssh_spec
from app.servers.models import Server
from app.tools.ansible_tool import AnsibleNotAvailable, run_playbook_step
from app.tools.aws_tool import AWSTool
from app.tools.ssh_tool import SSHTool


@dataclass
class ExecutionContext:
    server: Optional[Server] = None
    server_connection: Optional[Connection] = None
    cloud_connection: Optional[Connection] = None


@dataclass
class ToolResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    data: dict | None = None
    error: Optional[str] = None


def dispatch(task: CompiledTask, ctx: ExecutionContext, on_output: Callable[[str, str], None] | None = None) -> ToolResult:
    on_output = on_output or (lambda stream, line: None)

    if task.kind == "ansible":
        if not ctx.server or not ctx.server_connection:
            return ToolResult(False, error="Ansible task requires a resolved server + SSH connection")
        spec = resolve_ssh_spec(ctx.server_connection, ctx.server.hostname, ctx.server.port, ctx.server.username)
        try:
            result = run_playbook_step(
                task.payload, hostname=spec.hostname, port=spec.port, username=spec.username,
                password=spec.password, private_key=spec.private_key, on_output=on_output,
            )
            return ToolResult(result["success"], stdout=result["stdout"], stderr=result["stderr"], data={"changed": result["changed"]})
        except AnsibleNotAvailable as exc:
            return ToolResult(False, error=str(exc))

    if task.kind in ("ssh", "docker", "git"):
        if not ctx.server or not ctx.server_connection:
            return ToolResult(False, error=f"{task.kind} task requires a resolved server + SSH connection")
        spec = resolve_ssh_spec(ctx.server_connection, ctx.server.hostname, ctx.server.port, ctx.server.username)
        tool = SSHTool(spec)
        try:
            tool.connect()
            result = tool.run_streaming(task.payload, on_output=on_output)
            return ToolResult(result.success, stdout=result.stdout, stderr=result.stderr)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, error=str(exc))
        finally:
            tool.close()

    if task.kind == "aws":
        if not ctx.cloud_connection:
            return ToolResult(False, error="AWS task requires a resolved AWS connection")
        creds = resolve_aws_credentials(ctx.cloud_connection)
        tool = AWSTool(creds)
        action = task.payload["action"]
        params = task.payload["params"]
        method_map = {
            "list_regions": tool.list_regions, "list_instance_types": tool.list_instance_types,
            "list_amis": tool.list_amis, "list_vpcs": tool.list_vpcs, "list_subnets": tool.list_subnets,
            "list_security_groups": tool.list_security_groups, "list_instances": tool.list_instances,
            "list_s3_buckets": tool.list_s3_buckets, "list_rds_instances": tool.list_rds_instances,
            "run_instances": tool.run_instances, "terminate_instances": tool.terminate_instances,
            "create_vpc": tool.create_vpc,
        }
        try:
            data = method_map[action](**params) if params else method_map[action]()
            on_output("stdout", f"AWS {action} succeeded")
            return ToolResult(True, data=data if isinstance(data, dict) else {"result": data})
        except Exception as exc:  # noqa: BLE001
            on_output("stderr", f"AWS {action} failed: {exc}")
            return ToolResult(False, error=str(exc))

    if task.kind == "kubernetes":
        return ToolResult(False, error="Kubernetes execution requires a configured Kubernetes connection; see docs.")

    return ToolResult(False, error=f"No tool registered for kind '{task.kind}'")
