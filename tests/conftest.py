import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///" + str(Path(tempfile.mkdtemp(prefix="bangjach-tests-")) / "test.db"),
)
url = make_url(TEST_URL)
if url.drivername.startswith("postgresql") and (
    url.host not in {"127.0.0.1", "localhost"} or url.username != "bangjach_test"
):
    raise RuntimeError("Tests require a local disposable database owned by bangjach_test")
os.environ["DATABASE_URL"] = TEST_URL
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-only-secret-not-for-production-0123456789"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_MODEL"] = ""

from app.core.config import settings  # noqa: E402
from app.core.database import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migration():
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=os.environ.copy()
    )


@pytest_asyncio.fixture
async def factory(migration):
    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    async with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            await connection.execute(delete(table))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings.admin_user_ids = []
    settings.rate_limit_enabled = False
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(factory):
    async def session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def account(client, name="플레이어", number="01011111111"):
    payload = {"phone_number": number, "password": "test-password", "name": name}
    result = await client.post("/user/v1/sign-up", json=payload)
    assert result.status_code == 201, result.text
    login = await client.post(
        "/user/v1/log-in", json={k: payload[k] for k in ("phone_number", "password")}
    )
    assert login.status_code == 200, login.text
    data = login.json()
    return data["user"], {"Authorization": "Bearer " + data["access_token"]}, data


async def catalog(client):
    user, headers, tokens = await account(client, "관리자")
    settings.admin_user_ids = [user["id"]]
    result = await client.post(
        "/cafe/v1",
        headers=headers,
        json={
            "name": "테스트 카페",
            "website": "https://example.com",
            "phone_number": "021111111",
            "region": 1,
            "address": "서울",
        },
    )
    assert result.status_code == 201, result.text
    cafe = result.json()
    result = await client.post(
        "/theme/v1",
        headers=headers,
        json={
            "name": "첫 이야기",
            "cafe_id": cafe["id"],
            "description": "테스트 전용 테마",
            "length": 60,
        },
    )
    assert result.status_code == 201, result.text
    return user, headers, result.json(), cafe
