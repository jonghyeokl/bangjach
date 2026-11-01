import pytest

pytestmark = pytest.mark.asyncio


async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_web_cors(client):
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:8081"
