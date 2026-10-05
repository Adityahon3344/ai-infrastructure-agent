"""
Genuine integration tests against a real local SSH server (not a mock/stub).
These prove SSHTool, server discovery, verification, and file management
actually perform real SSH/SFTP operations end-to-end.

Skips automatically if no SSH server is reachable on 127.0.0.1:2222 with the
expected test credentials (e.g. in CI environments without sshd configured) —
see README "Testing" section for how to set this up locally.
"""
import os
import socket

import pytest

from app.tools.ssh_tool import SSHConnectionSpec, SSHTool

TEST_HOST = "127.0.0.1"
TEST_PORT = 2222
TEST_USER = "testuser"
TEST_PASSWORD = "testpass123"
TEST_KEY_PATH = "/tmp/test_key"


def _ssh_available() -> bool:
    try:
        with socket.create_connection((TEST_HOST, TEST_PORT), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _ssh_available(), reason="No local SSH server on 127.0.0.1:2222 for integration testing")


def _spec_password() -> SSHConnectionSpec:
    return SSHConnectionSpec(hostname=TEST_HOST, port=TEST_PORT, username=TEST_USER, password=TEST_PASSWORD)


def _spec_key() -> SSHConnectionSpec:
    key_text = open(TEST_KEY_PATH).read() if os.path.exists(TEST_KEY_PATH) else None
    return SSHConnectionSpec(hostname=TEST_HOST, port=TEST_PORT, username=TEST_USER, private_key=key_text)


def test_real_ssh_password_auth_and_command_execution():
    tool = SSHTool(_spec_password())
    tool.connect()
    try:
        result = tool.run("echo hello-from-real-ssh")
        assert result.success
        assert "hello-from-real-ssh" in result.stdout
    finally:
        tool.close()


def test_real_ssh_key_auth():
    if not os.path.exists(TEST_KEY_PATH):
        pytest.skip("No test private key available")
    tool = SSHTool(_spec_key())
    tool.connect()
    try:
        result = tool.run("whoami")
        assert result.stdout.strip() == TEST_USER
    finally:
        tool.close()


def test_real_ssh_streaming_output():
    tool = SSHTool(_spec_password())
    tool.connect()
    lines = []
    try:
        result = tool.run_streaming("echo line1 && echo line2 && echo line3", on_output=lambda stream, line: lines.append((stream, line)))
        assert result.success
        assert any("line1" in l for _, l in lines)
        assert any("line3" in l for _, l in lines)
    finally:
        tool.close()


def test_real_ssh_nonzero_exit_code_reported_as_failure():
    tool = SSHTool(_spec_password())
    tool.connect()
    try:
        result = tool.run("exit 7")
        assert not result.success
        assert result.exit_code == 7
    finally:
        tool.close()


def test_real_server_discovery_reads_actual_os_facts():
    from app.servers.discovery import discover_server

    result = discover_server(_spec_password())
    assert result.reachable
    assert result.architecture  # e.g. x86_64
    assert result.cpu_cores and result.cpu_cores > 0
    assert result.ram_mb and result.ram_mb > 0
    assert result.package_manager.strip() in ("apt", "dnf", "yum", "unknown")


def test_real_sftp_file_write_and_view_roundtrip(tmp_path):
    from app.files import service as file_service
    from app.servers.models import Server
    from app.connections.models import Connection, ConnectionType
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        conn = Connection(name="real-ssh-test", type=ConnectionType.SSH, config={"hostname": TEST_HOST, "port": TEST_PORT, "username": TEST_USER})
        from app.core.security import encrypt_secret
        import json
        conn.encrypted_credential = encrypt_secret(json.dumps({"password": TEST_PASSWORD}))
        db.add(conn)
        db.commit()
        db.refresh(conn)

        server = Server(name="real-ssh-server", hostname=TEST_HOST, port=TEST_PORT, username=TEST_USER, connection_id=conn.id)
        db.add(server)
        db.commit()
        db.refresh(server)

        remote_path = "/tmp/aia_integration_test_file.txt"
        result = file_service.write_file(db, server, conn, remote_path, "hello world\nsecond line\n", user_id="tester")
        assert result["success"]

        viewed = file_service.view_file(server, conn, remote_path)
        assert "hello world" in viewed["content"]

        # A second write should trigger a real backup of the previous content.
        file_service.write_file(db, server, conn, remote_path, "replaced content\n", user_id="tester")
        backups = file_service.list_backups(db, server.id, remote_path)
        assert len(backups) >= 1
        assert "hello world" in backups[0].content_snapshot or any("hello world" in b.content_snapshot for b in backups)
    finally:
        db.close()


def test_real_sftp_privileged_write_to_root_owned_path_via_sudo_fallback():
    """Regression test: writing to a root-owned path (e.g. under /opt) must
    fall back to a sudo-based write when plain SFTP gets Permission denied —
    this is the same real-world requirement Ansible's `become` covers for
    package/service actions, but for the file-management feature."""
    from app.files import service as file_service
    from app.servers.models import Server
    from app.connections.models import Connection, ConnectionType
    from app.core.database import SessionLocal
    from app.core.security import encrypt_secret
    import json

    root_owned_dir = "/opt/aia_priv_test"
    setup_tool = SSHTool(_spec_key() if os.path.exists(TEST_KEY_PATH) else _spec_password())
    setup_tool.connect()
    try:
        setup_tool.run(f"sudo rm -rf {root_owned_dir} && sudo mkdir -p {root_owned_dir} && sudo chown root:root {root_owned_dir}", timeout=15)
    finally:
        setup_tool.close()

    db = SessionLocal()
    try:
        conn = Connection(name="priv-write-test", type=ConnectionType.SSH, config={"hostname": TEST_HOST, "port": TEST_PORT, "username": TEST_USER})
        conn.encrypted_credential = encrypt_secret(json.dumps({"password": TEST_PASSWORD}))
        db.add(conn)
        db.commit()
        db.refresh(conn)

        server = Server(name="priv-write-server", hostname=TEST_HOST, port=TEST_PORT, username=TEST_USER, connection_id=conn.id)
        db.add(server)
        db.commit()
        db.refresh(server)

        remote_path = f"{root_owned_dir}/config.txt"
        result = file_service.write_file(db, server, conn, remote_path, "version=1", user_id="tester")
        assert result["success"], result

        viewed = file_service.view_file(server, conn, remote_path)
        assert viewed["content"] == "version=1"

        # Verify on the real filesystem, independent of our own read path.
        check_tool = SSHTool(_spec_password())
        check_tool.connect()
        try:
            owner_check = check_tool.run(f"stat -c '%U:%G' {remote_path}")
            assert owner_check.stdout.strip() == "root:root"
            content_check = check_tool.run(f"cat {remote_path}")
            assert content_check.stdout.strip() == "version=1"
        finally:
            check_tool.close()
    finally:
        db.close()
    from app.verification.verifier import verify_path_exists
    from app.servers.models import Server
    from app.connections.models import Connection, ConnectionType

    server = Server(id="s1", name="x", hostname=TEST_HOST, port=TEST_PORT, username=TEST_USER)
    conn = Connection(id="c1", name="x", type=ConnectionType.SSH)
    from app.core.security import encrypt_secret
    import json
    conn.encrypted_credential = encrypt_secret(json.dumps({"password": TEST_PASSWORD}))

    result = verify_path_exists(server, conn, "/tmp")
    assert result.verified

    result2 = verify_path_exists(server, conn, "/this/path/does/not/exist/at/all")
    assert not result2.verified


def test_real_ansible_task_execution_if_available():
    import shutil
    if not shutil.which("ansible-playbook"):
        pytest.skip("ansible-playbook not installed in this environment")

    from app.tools.ansible_tool import run_playbook_step

    playbook = """
- name: test file creation
  hosts: target
  gather_facts: false
  tasks:
    - name: create a test file
      file:
        path: /tmp/aia_ansible_test_marker
        state: touch
"""
    result = run_playbook_step(playbook, hostname=TEST_HOST, port=TEST_PORT, username=TEST_USER, password=TEST_PASSWORD)
    assert result["success"], result["stdout"]

    tool = SSHTool(_spec_password())
    tool.connect()
    try:
        check = tool.run("test -f /tmp/aia_ansible_test_marker && echo EXISTS")
        assert "EXISTS" in check.stdout
    finally:
        tool.close()
