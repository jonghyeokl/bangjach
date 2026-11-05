from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT, Settings
from app.domain.models import AuthSession, User


def test_repo_paths_do_not_depend_on_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///./data/bangjach.db",
        review_photo_local_dir="data/photos",
    )
    assert config.database_url == "sqlite+aiosqlite:///" + str(ROOT / "data/bangjach.db")
    assert config.review_photo_local_dir == str(ROOT / "data/photos")


@pytest.mark.asyncio
async def test_timezone_roundtrip_and_foreign_keys(factory):
    instant = datetime(2026, 11, 5, 9, 30, tzinfo=timezone(timedelta(hours=9)))
    async with factory() as db:
        user = User(phone_number="01077777777", name="UTC 검사", password_hash="fixture")
        db.add(user)
        await db.flush()
        db.add(AuthSession(user_id=user.id, refresh_token_hash="a" * 64, expires_dt=instant))
        await db.commit()
    async with factory() as db:
        session = await db.scalar(select(AuthSession))
        assert session.expires_dt == instant
        assert session.expires_dt.utcoffset() == timedelta(0)
        db.add(AuthSession(user_id=uuid4(), refresh_token_hash="b" * 64, expires_dt=instant))
        with pytest.raises(IntegrityError):
            await db.commit()
