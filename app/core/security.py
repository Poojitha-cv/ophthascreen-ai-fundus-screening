"""Password hashing (argon2id) and JWT access tokens."""
from __future__ import annotations

from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings
from app.core.database import utcnow

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("timing-equalisation-dummy")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def verify_dummy() -> None:
    """Burn comparable time when the user does not exist (avoids account enumeration by timing)."""
    verify_password(_DUMMY_HASH, "wrong-password")


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def create_access_token(user_id: str, role: str, settings: Settings) -> tuple[str, int]:
    now = utcnow()
    expires = timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": user_id, "role": role, "iat": int(now.timestamp()), "exp": now + expires}
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires.total_seconds())


def decode_access_token(token: str, settings: Settings) -> dict:
    """Raises jwt.PyJWTError on any problem."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm], options={"require": ["exp", "sub", "iat"]})
