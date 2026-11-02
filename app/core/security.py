import hashlib
import secrets
from datetime import timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_session
from app.core.errors import fail
from app.domain.models import AuthSession, User, now

DB = Annotated[AsyncSession, Depends(get_session)]
bearer = HTTPBearer(auto_error=False)
ph = PasswordHasher()
# Missing configuration never silently creates a shared production secret.
DEV_SECRET = secrets.token_urlsafe(48)


def secret():
    return settings.jwt_secret or DEV_SECRET


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def hash_password(value):
    return await run_in_threadpool(ph.hash, value)


async def verify_password(encoded, value):
    try:
        return await run_in_threadpool(ph.verify, encoded, value)
    except VerificationError:
        return False


async def identity(
    db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    if credentials is None:
        return None
    try:
        data = jwt.decode(
            credentials.credentials,
            secret(),
            algorithms=["HS256"],
            audience="bangjach",
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
        user_id, sid = UUID(data["sub"]), UUID(data["sid"])
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        fail(401, "UNAUTHORIZED", "다시 로그인하세요.")
    session = await db.get(AuthSession, sid)
    if (
        not session
        or session.user_id != user_id
        or session.revoked_dt
        or utc(session.expires_dt) <= now()
    ):
        fail(401, "UNAUTHORIZED", "로그인이 만료되었습니다.")
    user = await db.get(User, user_id)
    if not user:
        fail(401, "UNAUTHORIZED", "다시 로그인하세요.")
    return user, session


Identity = Annotated[tuple | None, Depends(identity)]


async def current_user(who: Identity):
    if not who:
        fail(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    return who[0]


CurrentUser = Annotated[User, Depends(current_user)]


async def admin(user: CurrentUser):
    if str(user.id) not in settings.admin_user_ids:
        fail(403, "ADMIN_REQUIRED", "관리자만 사용할 수 있습니다.")
    return user


Admin = Annotated[User, Depends(admin)]


async def tokens(db, user, session=None):
    refresh = secrets.token_urlsafe(48)
    if session is None:
        session = AuthSession(
            user_id=user.id, expires_dt=now() + timedelta(days=settings.refresh_token_days)
        )
        db.add(session)
    session.refresh_token_hash = token_hash(refresh)
    await db.flush()
    access = jwt.encode(
        {
            "sub": str(user.id),
            "sid": str(session.id),
            "iat": now(),
            "exp": now() + timedelta(minutes=settings.access_token_minutes),
            "aud": "bangjach",
        },
        secret(),
        algorithm="HS256",
    )
    await db.commit()
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
        "user": {
            "id": user.id,
            "phone_number": user.phone_number,
            "is_admin": str(user.id) in settings.admin_user_ids,
            "name": user.name,
            "created_dt": user.created_dt,
            "updated_dt": user.updated_dt,
        },
    }


async def lock_pair(db, first, second):
    # Lock the same rows in stable order for requests, accepts and removals.
    await db.execute(
        select(User.id).where(User.id.in_([first, second])).order_by(User.id).with_for_update()
    )
