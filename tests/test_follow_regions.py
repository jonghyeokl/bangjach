import pytest
from conftest import account, catalog
from test_feed_photos import image_bytes

from app.core.config import settings

pytestmark = pytest.mark.asyncio


async def test_private_defaults_and_photo_access(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "review_photo_local_dir", str(tmp_path))
    monkeypatch.setattr(settings, "review_photo_bucket", "")
    _, admin, theme, _ = await catalog(client)
    author, ah, _ = await account(client, "비공개", "01055555555", private=True)
    viewer, vh, _ = await account(client, "팔로워", "01066666666", private=True)
    assert (await client.get("/user/v1/me/settings", headers=ah)).json()["is_private"] is True
    photo = (await client.post("/media/v1/review-photos", headers=ah, content=image_bytes())).json()
    result = await client.post(
        "/review/v1",
        headers=ah,
        json={
            "theme_id": theme["id"],
            "rating": 4,
            "date": "2026-11-05",
            "photo_ids": [photo["id"]],
        },
    )
    assert result.status_code == 201
    for headers in ({}, vh, admin):
        assert (await client.get(photo["url"], headers=headers)).status_code == 403
    assert (await client.get(photo["url"], headers=ah)).status_code == 200
    req = (await client.post("/follow/v1", headers=vh, json={"user_id": author["id"]})).json()
    assert (await client.get(photo["url"], headers=vh)).status_code == 403
    await client.post(f"/follow/v1/{req['id']}/accept", headers=ah)
    assert (await client.get(photo["url"], headers=vh)).status_code == 200
    await client.delete(f"/follow/v1/{req['id']}", headers=vh)
    assert (await client.get(photo["url"], headers=vh)).status_code == 403
    await client.patch("/user/v1/me/settings", headers=ah, json={"is_private": False})
    assert (await client.get(photo["url"])).status_code == 200
    await client.patch("/user/v1/me/settings", headers=ah, json={"is_private": True})
    assert (await client.get(photo["url"])).status_code == 403


async def test_subregions_and_played_marker(client):
    _, headers, first, cafe = await catalog(client)
    meta = (await client.get("/meta/v1/enums")).json()
    hongdae = next(o for o in meta["subregion"] if o["label"] == "홍대")
    assert hongdae["parent"] == 1
    body = {
        "name": "홍대 지점",
        "phone_number": "02",
        "region": 1,
        "subregion": hongdae["value"],
        "address": "서울 마포구",
    }
    assert (
        await client.post("/cafe/v1", headers=headers, json={**body, "region": 2})
    ).status_code == 422
    assert (
        await client.post("/cafe/v1", headers=headers, json={**body, "subregion": 199})
    ).status_code == 422
    cafe = (await client.post("/cafe/v1", headers=headers, json=body)).json()
    theme = (
        await client.post(
            "/theme/v1",
            headers=headers,
            json={"name": "홍대 테마", "cafe_id": cafe["id"], "description": "테마", "length": 60},
        )
    ).json()
    rows = (
        await client.get("/theme/v1", params={"subregion": hongdae["value"]}, headers=headers)
    ).json()["items"]
    assert [t["id"] for t in rows] == [theme["id"]]
    assert rows[0]["is_played"] is False
    review = (
        await client.post(
            "/review/v1",
            headers=headers,
            json={"theme_id": theme["id"], "rating": 4, "date": "2026-11-05"},
        )
    ).json()
    rows = (await client.get("/theme/v1", headers=headers)).json()["items"]
    assert {t["id"]: t["is_played"] for t in rows} == {theme["id"]: True, first["id"]: False}
    assert not any(t["is_played"] for t in (await client.get("/theme/v1")).json()["items"])
    await client.delete(f"/review/v1/{review['id']}", headers=headers)
    assert not any(
        t["is_played"] for t in (await client.get("/theme/v1", headers=headers)).json()["items"]
    )
