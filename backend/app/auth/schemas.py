from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.auth.models import Role


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""
    role: Role = Role.OPERATOR


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: Role
    is_active: bool

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
