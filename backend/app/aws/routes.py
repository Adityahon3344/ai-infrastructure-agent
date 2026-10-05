"""
Dynamic AWS resource discovery endpoints. Every list is fetched live from the
AWS API through AWSTool — nothing here is a hard-coded catalog of instance
types/AMIs/etc. Mutating actions (provisioning, termination) are NOT exposed
directly here; they go through the agent -> PlanSpec -> validation -> risk ->
approval pipeline like every other action (see app.agent.orchestrator and
POST /api/chat), so a HIGH-risk action like terminating an instance can never
bypass approval by hitting a raw AWS endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security_deps import get_current_user
from app.connections.models import Connection, ConnectionType
from app.connections.service import resolve_aws_credentials
from app.core.database import get_db
from app.tools.aws_tool import AWSPermissionError, AWSTool

router = APIRouter(prefix="/api/aws", tags=["aws"])


def _tool(db: Session, connection_id: str) -> AWSTool:
    conn = db.get(Connection, connection_id)
    if not conn or conn.type != ConnectionType.AWS:
        raise HTTPException(404, "AWS connection not found")
    try:
        return AWSTool(resolve_aws_credentials(conn))
    except AWSPermissionError as exc:
        raise HTTPException(400, str(exc))


@router.get("/regions")
def regions(connection_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_regions()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/instance-types")
def instance_types(connection_id: str, min_vcpu: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_instance_types(min_vcpu=min_vcpu)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/amis")
def amis(connection_id: str, name_filter: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_amis(name_filter=name_filter)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/vpcs")
def vpcs(connection_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_vpcs()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/subnets")
def subnets(connection_id: str, vpc_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_subnets(vpc_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/security-groups")
def security_groups(connection_id: str, vpc_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_security_groups(vpc_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/instances")
def instances(connection_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_instances()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/s3-buckets")
def s3_buckets(connection_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_s3_buckets()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))


@router.get("/rds-instances")
def rds_instances(connection_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return _tool(db, connection_id).list_rds_instances()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, str(exc))
