from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.models import User
from app.auth.security_deps import get_current_user
from app.catalog.catalog import list_catalog

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("")
def get_catalog(_: User = Depends(get_current_user)):
    return list_catalog()
