"""
Rollback strategies, scoped honestly to what is technically possible:

- Configuration files: restored from FileBackup snapshots taken before every
  write (see app.files.service) — always possible, full content restore.
- Application deployments: tracked as DeploymentVersion rows; rollback
  re-checks-out a previous git ref into the same deploy path.
- Infrastructure (AWS resources provisioned directly via boto3): destructive
  changes (e.g. terminated EC2 instances, deleted volumes) are NOT reversible,
  and this module never claims otherwise.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.connections.models import Connection
from app.connections.service import resolve_ssh_spec
from app.rollback.models import DeploymentVersion
from app.servers.models import Server
from app.tools.ssh_tool import SSHTool


def record_deployment(db: Session, server_id: str, deploy_path: str, job_id: str, repo_url: str, git_ref: str) -> DeploymentVersion:
    version = DeploymentVersion(server_id=server_id, deploy_path=deploy_path, job_id=job_id, repo_url=repo_url, git_ref=git_ref)
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def list_versions(db: Session, server_id: str, deploy_path: str) -> list[DeploymentVersion]:
    return (
        db.query(DeploymentVersion)
        .filter(DeploymentVersion.server_id == server_id, DeploymentVersion.deploy_path == deploy_path)
        .order_by(DeploymentVersion.created_at.desc())
        .all()
    )


def rollback_deployment(db: Session, server: Server, connection: Connection, version_id: str) -> dict:
    version = db.get(DeploymentVersion, version_id)
    if not version:
        raise ValueError("Deployment version not found")
    if not version.git_ref:
        raise ValueError("This deployment has no recorded git ref and cannot be rolled back automatically.")

    spec = resolve_ssh_spec(connection, server.hostname, server.port, server.username)
    tool = SSHTool(spec)
    try:
        tool.connect()
        result = tool.run(f"cd {version.deploy_path} && git checkout {version.git_ref}", timeout=60)
        return {"success": result.success, "stdout": result.stdout, "stderr": result.stderr, "restored_ref": version.git_ref}
    finally:
        tool.close()
