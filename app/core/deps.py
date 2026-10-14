"""FastAPI dependencies: db session, settings, current user, role guards, shared services."""
from __future__ import annotations

from collections.abc import Iterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decode_access_token
from app.modules.auth.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db: Session = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_storage(request: Request):
    return request.app.state.storage


def get_engine(request: Request):
    """The loaded inference engine, or None if the model is unavailable."""
    return request.app.state.engine


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings_dep)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_access_token(token, settings)
    except jwt.PyJWTError:
        raise unauthorized
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise unauthorized
    if user.password_changed_at and payload["iat"] < int(user.password_changed_at.timestamp()):
        raise unauthorized  # token predates a password change
    return user


def require_doctor(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.DOCTOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctor role required")
    return user
