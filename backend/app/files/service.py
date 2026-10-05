"""
Controlled remote file management over SFTP (via the same SSH connection used
for everything else). Every write is preceded by a backup of the previous
content so a diff/restore is always possible. Sensitive files (anything that
looks like it holds credentials) are never returned to the frontend in full.
"""
from __future__ import annotations

import difflib
import posixpath
import re
import shlex
import stat
import uuid

from sqlalchemy.orm import Session

from app.connections.models import Connection
from app.connections.service import resolve_ssh_spec
from app.files.models import FileBackup
from app.servers.models import Server
from app.tools.ssh_tool import SSHTool

SENSITIVE_PATH_PATTERNS = [
    re.compile(r"(?i)/(id_rsa|id_ed25519|\.pem|\.key)$"),
    re.compile(r"(?i)/\.ssh/"),
    re.compile(r"(?i)/(shadow|gshadow)$"),
    re.compile(r"(?i)\.env$"),
    re.compile(r"(?i)/secrets?/"),
]


def is_sensitive_path(path: str) -> bool:
    return any(p.search(path) for p in SENSITIVE_PATH_PATTERNS)


def _ssh(server: Server, connection: Connection) -> SSHTool:
    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    tool.connect()
    return tool


def _sudo_read(tool: SSHTool, path: str) -> str:
    """Privileged read fallback for files the SSH user can't access directly
    over plain SFTP (e.g. root-owned files/paths under /etc, /opt). Requires
    passwordless sudo for the connecting user — the same requirement Ansible
    `become` already relies on elsewhere in this project."""
    result = tool.run(f"sudo cat {shlex.quote(path)}", timeout=30)
    if not result.success:
        raise IOError(result.stderr or "Permission denied (sudo read also failed)")
    return result.stdout


def _sudo_write(tool: SSHTool, sftp, path: str, content: str) -> None:
    """Privileged write fallback: stage the content in a temp file the SSH
    user CAN write (/tmp), then move it into place with sudo, preserving
    root:root ownership consistent with how Ansible's `become`-run file
    actions leave files elsewhere in this project."""
    tmp_remote = f"/tmp/aia_upload_{uuid.uuid4().hex}"
    with sftp.open(tmp_remote, "w") as f:
        f.write(content)
    result = tool.run(
        f"sudo mv {shlex.quote(tmp_remote)} {shlex.quote(path)} && sudo chown root:root {shlex.quote(path)}",
        timeout=30,
    )
    if not result.success:
        tool.run(f"rm -f {shlex.quote(tmp_remote)}", timeout=10)
        raise IOError(result.stderr or "Permission denied (sudo write also failed)")


def browse(server: Server, connection: Connection, path: str) -> list[dict]:
    tool = _ssh(server, connection)
    try:
        try:
            sftp = tool.open_sftp()
            entries = []
            for attr in sftp.listdir_attr(path):
                entries.append({
                    "name": attr.filename,
                    "path": posixpath.join(path, attr.filename),
                    "is_dir": stat.S_ISDIR(attr.st_mode or 0),
                    "size": attr.st_size,
                    "modified": attr.st_mtime,
                    "sensitive": is_sensitive_path(posixpath.join(path, attr.filename)),
                })
            return sorted(entries, key=lambda e: (not e["is_dir"], e["name"]))
        except (IOError, PermissionError):
            # Privileged directory listing fallback (e.g. root-only directories).
            result = tool.run(
                f"sudo find {shlex.quote(path)} -mindepth 1 -maxdepth 1 -printf '%f\\t%y\\t%s\\t%T@\\n'", timeout=30,
            )
            if not result.success:
                raise IOError(result.stderr or "Permission denied listing directory")
            entries = []
            for line in result.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) != 4:
                    continue
                name, ftype, size, mtime = parts
                entries.append({
                    "name": name,
                    "path": posixpath.join(path, name),
                    "is_dir": ftype == "d",
                    "size": int(size) if size.isdigit() else 0,
                    "modified": float(mtime) if mtime else 0,
                    "sensitive": is_sensitive_path(posixpath.join(path, name)),
                })
            return sorted(entries, key=lambda e: (not e["is_dir"], e["name"]))
    finally:
        tool.close()


def view_file(server: Server, connection: Connection, path: str, max_bytes: int = 200_000) -> dict:
    if is_sensitive_path(path):
        return {"path": path, "sensitive": True, "content": None, "message": "This file is treated as sensitive and its contents are masked."}
    tool = _ssh(server, connection)
    try:
        try:
            sftp = tool.open_sftp()
            with sftp.open(path, "r") as f:
                data = f.read(max_bytes)
            content = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
        except (IOError, PermissionError):
            content = _sudo_read(tool, path)[:max_bytes]
        return {"path": path, "sensitive": False, "content": content, "truncated": len(content) >= max_bytes}
    finally:
        tool.close()


def write_file(db: Session, server: Server, connection: Connection, path: str, content: str, user_id: str | None) -> dict:
    if is_sensitive_path(path):
        raise PermissionError("Refusing to write to a path classified as sensitive.")

    tool = _ssh(server, connection)
    previous = ""
    try:
        sftp = tool.open_sftp()
        try:
            with sftp.open(path, "r") as f:
                previous = f.read().decode("utf-8", errors="replace")
        except IOError:
            try:
                previous = _sudo_read(tool, path)
            except IOError:
                previous = ""  # genuinely doesn't exist yet (new file)

        db.add(FileBackup(server_id=server.id, remote_path=path, content_snapshot=previous, created_by=user_id))
        db.commit()

        try:
            with sftp.open(path, "w") as f:
                f.write(content)
        except (IOError, PermissionError):
            _sudo_write(tool, sftp, path, content)

        diff = "\n".join(difflib.unified_diff(previous.splitlines(), content.splitlines(), lineterm=""))
        return {"success": True, "diff": diff}
    finally:
        tool.close()


def list_backups(db: Session, server_id: str, path: str | None = None) -> list[FileBackup]:
    query = db.query(FileBackup).filter(FileBackup.server_id == server_id)
    if path:
        query = query.filter(FileBackup.remote_path == path)
    return query.order_by(FileBackup.created_at.desc()).all()


def restore_backup(db: Session, server: Server, connection: Connection, backup_id: str) -> dict:
    backup = db.get(FileBackup, backup_id)
    if not backup:
        raise ValueError("Backup not found")
    return write_file(db, server, connection, backup.remote_path, backup.content_snapshot, backup.created_by)
