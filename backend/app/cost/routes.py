from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security_deps import get_current_user
from app.connections.models import Connection, ConnectionType
from app.connections.service import resolve_aws_credentials
from app.core.database import get_db
from app.cost.estimator import estimate_ec2_monthly_cost
from app.tools.aws_tool import AWSTool

router = APIRouter(prefix="/api/cost", tags=["cost"])


@router.get("/ec2")
def ec2_cost(connection_id: str, instance_type: str, ebs_gb: int = 20, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    conn = db.get(Connection, connection_id)
    if not conn or conn.type != ConnectionType.AWS:
        raise HTTPException(404, "AWS connection not found")
    tool = AWSTool(resolve_aws_credentials(conn))
    estimate = estimate_ec2_monthly_cost(tool, instance_type, tool.region, ebs_gb)
    return {
        "instance_type": instance_type, "region": tool.region, "monthly_usd": estimate.monthly_usd,
        "hourly_usd": estimate.hourly_usd, "is_estimate": estimate.is_estimate, "source": estimate.source,
        "note": estimate.note,
    }
