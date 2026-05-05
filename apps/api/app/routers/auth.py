import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import CurrentUser
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    UserSchema,
)
from app.schemas.common import ApiResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.jwt_refresh_expire_days * 86400,
        path="/api/v1/auth",
    )


@router.post("/register", response_model=ApiResponse[AuthResponse], status_code=201)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if await auth_service.get_user_by_email(db, body.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = await auth_service.create_user(db, body.email, body.password, body.name)
    access = auth_service.create_access_token(str(user.id))
    refresh = auth_service.create_refresh_token(str(user.id))
    _set_refresh_cookie(response, refresh)

    return ApiResponse(data=AuthResponse(
        access_token=access,
        user=UserSchema.model_validate(user),
    ))


@router.post("/login", response_model=ApiResponse[AuthResponse])
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.get_user_by_email(db, body.email)
    if not user or not auth_service.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    access = auth_service.create_access_token(str(user.id))
    refresh = auth_service.create_refresh_token(str(user.id))
    _set_refresh_cookie(response, refresh)

    return ApiResponse(data=AuthResponse(
        access_token=access,
        user=UserSchema.model_validate(user),
    ))


@router.post("/refresh", response_model=ApiResponse[RefreshResponse])
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    try:
        payload = auth_service.decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError
        user_id = payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await auth_service.get_user_by_id(db, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_access = auth_service.create_access_token(str(user.id))
    new_refresh = auth_service.create_refresh_token(str(user.id))
    _set_refresh_cookie(response, new_refresh)

    return ApiResponse(data=RefreshResponse(access_token=new_access))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return ApiResponse(data={"message": "Logged out"})


@router.get("/me", response_model=ApiResponse[UserSchema])
async def me(current_user: CurrentUser):
    return ApiResponse(data=UserSchema.model_validate(current_user))
