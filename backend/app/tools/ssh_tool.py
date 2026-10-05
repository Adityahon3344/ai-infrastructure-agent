"""Real SSH execution via paramiko. This is the lowest-level primitive that
AnsibleTool, file management, terminal, and monitoring all build on top of.

Security notes:
- Host keys are recorded with AutoAddPolicy for usability in a lab/dev context.
  For production, wire this to a known_hosts file / TOFU-with-pinning policy.
- Credentials never appear in logs: SSHConnectionSpec.__repr__ is overridden.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

import paramiko

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("tools.ssh")


@dataclass
class SSHConnectionSpec:
    hostname: str
    port: int = 22
    username: str = "root"
    password: Optional[str] = None
    private_key: Optional[str] = None  # PEM text, decrypted just-in-time by caller
    private_key_passphrase: Optional[str] = None
    connect_timeout: int = field(default_factory=lambda: settings.ssh_connect_timeout_seconds)

    def __repr__(self) -> str:  # never leak secrets accidentally via logging/debug
        return f"SSHConnectionSpec(hostname={self.hostname!r}, port={self.port}, username={self.username!r}, auth=***)"


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SSHTool:
    """One SSHTool instance = one live connection lifecycle."""

    def __init__(self, spec: SSHConnectionSpec):
        self.spec = spec
        self._client: Optional[paramiko.SSHClient] = None

    def connect(self) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = {
            "hostname": self.spec.hostname,
            "port": self.spec.port,
            "username": self.spec.username,
            "timeout": self.spec.connect_timeout,
            "banner_timeout": self.spec.connect_timeout,
            "auth_timeout": self.spec.connect_timeout,
        }
        if self.spec.private_key:
            pkey = self._load_private_key(self.spec.private_key, self.spec.private_key_passphrase)
            kwargs["pkey"] = pkey
        elif self.spec.password:
            kwargs["password"] = self.spec.password
        else:
            raise ValueError("SSH connection requires either a password or a private key")

        client.connect(**kwargs)
        self._client = client
        logger.info(f"SSH connected to {self.spec.hostname}:{self.spec.port} as {self.spec.username}")

    @staticmethod
    def _load_private_key(pem_text: str, passphrase: str | None):
        key_classes = [paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey]
        last_err = None
        for cls in key_classes:
            try:
                return cls.from_private_key(io.StringIO(pem_text), password=passphrase)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        raise ValueError(f"Unable to parse private key with any supported algorithm: {last_err}")

    def run(self, command: str, timeout: int | None = None, env: dict | None = None) -> CommandResult:
        if not self._client:
            raise RuntimeError("SSHTool.connect() must be called before run()")
        timeout = timeout or settings.command_timeout_seconds
        try:
            stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout, environment=env or {})
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            return CommandResult(command=command, exit_code=exit_code, stdout=out, stderr=err)
        except TimeoutError:
            return CommandResult(command=command, exit_code=-1, stdout="", stderr="Command timed out", timed_out=True)

    def run_streaming(self, command: str, on_output, timeout: int | None = None) -> CommandResult:
        """Streams stdout/stderr line-by-line to `on_output(stream, line)` as the
        command runs, instead of buffering until completion. Used by execution
        engine + terminal so the frontend gets live output."""
        if not self._client:
            raise RuntimeError("SSHTool.connect() must be called before run_streaming()")
        timeout = timeout or settings.command_timeout_seconds
        transport = self._client.get_transport()
        channel = transport.open_session(timeout=timeout)
        channel.settimeout(timeout)
        channel.exec_command(command)

        stdout_buf, stderr_buf = [], []
        import time as _time
        start = _time.time()
        timed_out = False
        while True:
            if channel.recv_ready():
                chunk = channel.recv(4096).decode(errors="replace")
                for line in chunk.splitlines():
                    on_output("stdout", line)
                stdout_buf.append(chunk)
            if channel.recv_stderr_ready():
                chunk = channel.recv_stderr(4096).decode(errors="replace")
                for line in chunk.splitlines():
                    on_output("stderr", line)
                stderr_buf.append(chunk)
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            if _time.time() - start > timeout:
                timed_out = True
                channel.close()
                break
            _time.sleep(0.05)

        exit_code = channel.recv_exit_status() if not timed_out else -1
        return CommandResult(
            command=command,
            exit_code=exit_code,
            stdout="".join(stdout_buf),
            stderr="".join(stderr_buf),
            timed_out=timed_out,
        )

    def open_sftp(self):
        if not self._client:
            raise RuntimeError("SSHTool.connect() must be called before open_sftp()")
        return self._client.open_sftp()

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
