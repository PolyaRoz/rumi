import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)
    name: str | None = Field(None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserSchema(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    plan: str
    generations_used: int
    generations_limit: int
    avatar_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSchema


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
