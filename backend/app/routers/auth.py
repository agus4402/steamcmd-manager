"""Authentication endpoints + the dependency used to protect the API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

bearer = HTTPBearer(auto_error=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


async def require_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
) -> str:
    """FastAPI dependency: validate the bearer token, return the username."""
    username = auth_service.decode_token(creds.credentials)
    if username is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return username


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await auth_service.authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return TokenResponse(access_token=auth_service.create_access_token(user.username))


@router.get("/me")
async def me(username: str = Depends(require_user)) -> dict[str, str]:
    return {"username": username}
