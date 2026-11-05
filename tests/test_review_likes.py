import asyncio
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import account, catalog
from sqlalchemy import func, select

from app.api import reviews
from app.domain.models import Review, ReviewLike, Theme, now


async def write_review(client, headers, theme):
    result = await client.post(
        "/review/v1",
        headers=headers,
        json={"theme_id": theme["id"], "rating": 4, "date": "2026-11-01"},
    )
    assert result.status_code == 201, result.text
    return result.json()


@pytest.mark.asyncio
async def test_likes_idempotent_concurrent_scoped_and_cascade(client, factory):
    author, ah, theme, _ = await catalog(client)
    viewer, vh, _ = await account(client, "읽는사람", "01022222222")
    review = await write_review(client, ah, theme)
    path = f"/review/v1/{review['id']}"
    assert review["like_count"] == 0 and review["is_liked"] is False
    assert (await client.put(path + "/like")).status_code == 401
    assert (await client.put(f"/review/v1/{uuid4()}/like", headers=vh)).status_code == 404
    # Retries/concurrent requests cannot produce duplicate likes.
    results = await asyncio.gather(*[client.put(path + "/like", headers=vh) for _ in range(3)])
    for result in results:
        assert result.status_code == 200, result.text
        assert result.json() == {"review_id": review["id"], "like_count": 1, "is_liked": True}
    await client.put(path + "/like", headers=ah)
    assert (await client.get(path)).json()["is_liked"] is False
    for url in [
        path,
        f"/review/v1?theme_id={theme['id']}",
        f"/user/v1/{author['id']}/reviews",
        "/feed/v1?scope=all",
    ]:
        body = (await client.get(url, headers=vh)).json()
        item = body if url == path else next(r for r in body["items"] if r["id"] == review["id"])
        assert item["like_count"] == 2 and item["is_liked"] is True
    own = (await client.get("/user/v1/me/reviews", headers=ah)).json()["items"][0]
    assert own["like_count"] == 2 and own["is_liked"] is True
    # An unlike only removes the caller's like and is safe to retry.
    for _ in range(2):
        result = await client.delete(path + "/like", headers=vh)
        assert result.json()["like_count"] == 1
        assert result.json()["is_liked"] is False
    await client.delete(path, headers=ah)
    async with factory() as db:
        assert await db.scalar(select(func.count(ReviewLike.id))) == 0
    assert (await client.delete(path + "/like", headers=vh)).status_code == 404


@pytest.mark.asyncio
async def test_private_review_likes_require_accepted_follow(client):
    author, ah, theme, _ = await catalog(client)
    _, vh, _ = await account(client, "팔로워", "01022222222")
    review = await write_review(client, ah, theme)
    path = f"/review/v1/{review['id']}/like"
    await client.patch("/user/v1/me/settings", headers=ah, json={"is_private": True})
    assert (await client.put(path, headers=vh)).status_code == 403
    follow = (await client.post("/follow/v1", headers=vh, json={"user_id": author["id"]})).json()
    assert (await client.put(path, headers=vh)).status_code == 403
    await client.post(f"/follow/v1/{follow['id']}/accept", headers=ah)
    assert (await client.put(path, headers=vh)).json()["is_liked"] is True
    await client.delete(f"/follow/v1/{follow['id']}", headers=vh)
    assert (await client.put(path, headers=vh)).status_code == 403
    assert (await client.delete(path, headers=vh)).status_code == 403


@pytest.mark.asyncio
async def test_feed_scopes_30_day_boundary_sort_and_pagination(client, factory, monkeypatch):
    owner, oh, _, cafe = await catalog(client)
    followed, fh, _ = await account(client, "승인팔로잉", "01022222222", private=True)
    public, ph, _ = await account(client, "공개계정", "01033333333")
    pending, _, _ = await account(client, "승인대기", "01044444444", private=True)
    hidden, _, _ = await account(client, "비공개", "01055555555", private=True)
    req = (await client.post("/follow/v1", headers=oh, json={"user_id": followed["id"]})).json()
    await client.post(f"/follow/v1/{req['id']}/accept", headers=fh)
    await client.post("/follow/v1", headers=oh, json={"user_id": pending["id"]})
    anchor = now()
    monkeypatch.setattr(reviews, "now", lambda: anchor)
    ids = {}
    async with factory() as db:
        for name, user, age in [
            ("own", owner, timedelta(hours=1)),
            ("followed", followed, timedelta(hours=2)),
            ("public", public, timedelta(hours=3)),
            ("pending", pending, timedelta(minutes=1)),
            ("hidden", hidden, timedelta(minutes=2)),
            ("boundary", public, timedelta(days=30)),
            ("too_old", followed, timedelta(days=30, microseconds=1)),
            ("old_public", public, timedelta(days=31)),
            ("future", public, timedelta(seconds=-1)),
        ]:
            theme = Theme(cafe_id=UUID(cafe["id"]), name=name, description="", length=60)
            db.add(theme)
            await db.flush()
            row = Review(
                user_id=UUID(user["id"]),
                theme_id=theme.id,
                rating=4,
                date=date(2026, 1, 1),
                created_dt=anchor - age,
                updated_dt=anchor,
            )
            db.add(row)
            await db.flush()
            ids[name] = str(row.id)
        await db.commit()

    async def feed(params=""):
        result = await client.get("/feed/v1" + params, headers=oh)
        assert result.status_code == 200, result.text
        return result.json()

    assert [r["id"] for r in (await feed())["items"]] == [ids["followed"]]
    expected = [ids[k] for k in ["own", "followed", "public", "boundary"]]
    all_rows = await feed("?scope=all")
    assert all_rows["total"] == 4
    assert [r["id"] for r in all_rows["items"]] == expected
    await client.put(f"/review/v1/{ids['public']}/like", headers=oh)
    await client.put(f"/review/v1/{ids['public']}/like", headers=ph)
    first = await feed("?scope=all&sort=likes&page_size=2")
    second = await feed("?scope=all&sort=likes&page_size=2&page=2")
    assert first["total"] == second["total"] == 4
    assert [r["id"] for r in first["items"] + second["items"]] == [
        ids[k] for k in ["public", "own", "followed", "boundary"]
    ]
    assert first["items"][0]["like_count"] == 2
    assert [r["id"] for r in (await feed("?scope=following&sort=likes"))["items"]] == [
        ids["followed"]
    ]
    # Privacy changes take effect immediately, even for popular reviews.
    await client.patch("/user/v1/me/settings", headers=ph, json={"is_private": True})
    assert (await feed("?scope=all&sort=likes"))["total"] == 2
    await client.delete(f"/follow/v1/{req['id']}", headers=oh)
    assert (await feed())["total"] == 0
    assert (await feed("?scope=all"))["total"] == 1
    assert (await client.get("/feed/v1?scope=bad", headers=oh)).status_code == 422
    assert (await client.get("/feed/v1?sort=bad", headers=oh)).status_code == 422
