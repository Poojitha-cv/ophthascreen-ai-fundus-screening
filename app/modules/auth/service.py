from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import utcnow
from app.core.security import hash_password, needs_rehash, verify_dummy, verify_password
from app.modules.auth.models import Role, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def create_user(db: Session, *, email: str, password: str, full_name: str, role: Role) -> User:
    user = User(email=normalize_email(email), password_hash=hash_password(password), full_name=full_name.strip(), role=role)
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str, settings: Settings) -> tuple[User | None, str]:
    """Returns (user, outcome). outcome: ok | unknown_user | locked | bad_password | inactive.
    Updates lockout counters; the caller commits."""
    user = get_user_by_email(db, email)
    if user is None:
        verify_dummy()
        return None, "unknown_user"
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        return None, "locked"
    if not verify_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_count = 0
        return None, "bad_password"
    if not user.is_active:
        return None, "inactive"
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    return user, "ok"
