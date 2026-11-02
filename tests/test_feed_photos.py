from datetime import date, datetime, timezone
from io import BytesIO
from uuid import UUID

import pytest
from conftest import account, catalog
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.domain.models import Review, ReviewPhoto, Theme


def image_bytes():
    stream = BytesIO()
    Image.new("RGB", (1800, 900), "green").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture(autouse=True)
def local_photos(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "review_photo_bucket", "")
    monkeypatch.setattr(settings, "review_photo_local_dir", str(tmp_path))


@pytest.mark.asyncio
async def test_feed_is_authenticated_friends_only_newest_first(client, factory):
    owner, headers, theme, _ = await catalog(client)
    friend_a, a_headers, _ = await account(client, "친구A", "01022222222")
    friend_b, b_headers, _ = await account(client, "친구B", "01033333333")
    stranger, s_headers, _ = await account(client, "요청대기", "01044444444")
    assert (await client.get("/feed/v1")).status_code == 401
    assert (await client.get("/feed/v1", headers=headers)).json()["items"] == []
    for other, other_headers in [(friend_a, a_headers), (friend_b, b_headers)]:
        req = await client.post(
            "/friend-request/v1", headers=headers, json={"requested_user_name": other["name"]}
        )
        assert (
            await client.post(
                f"/friend-request/v1/{req.json()['id']}/accept", headers=other_headers
            )
        ).status_code == 200
    await client.post(
        "/friend-request/v1", headers=headers, json={"requested_user_name": stranger["name"]}
    )
    async with factory() as db:
        target = await db.get(Theme, UUID(theme["id"]))
        target.image_url = "https://example.com/theme.jpg"
        for index, user in enumerate([owner, friend_a, friend_b, stranger]):
            db.add(
                Review(
                    user_id=UUID(user["id"]),
                    theme_id=target.id,
                    rating=4.5,
                    date=date(2026, 1, 5 - index),
                    content=user["name"],
                    created_dt=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
                )
            )
        await db.commit()
    response = await client.get("/feed/v1?page_size=1", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    item = response.json()["items"][0]
    assert item["author"]["id"] == friend_b["id"]
    assert item["theme_image_url"] == "https://example.com/theme.jpg"
    assert item["theme_name"] == theme["name"]
    assert item["rating"] == 4.5
    assert item["content"] == friend_b["name"]
    page2 = (await client.get("/feed/v1?page_size=1&page=2", headers=headers)).json()
    assert page2["items"][0]["author"]["id"] == friend_a["id"]
    # Changing a review does not move it above a more recently published review.
    async with factory() as db:
        row = await db.scalar(select(Review).where(Review.user_id == UUID(friend_a["id"])))
        row.updated_dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
        await db.commit()
    assert (await client.get("/feed/v1", headers=headers)).json()["items"][0]["id"] == item["id"]
    friends = (await client.get("/friend/v1", headers=headers)).json()["items"]
    for friend in friends:
        await client.delete("/friend/v1/" + friend["id"], headers=headers)
    assert (await client.get("/feed/v1", headers=headers)).json()["total"] == 0


@pytest.mark.asyncio
async def test_photo_upload_attach_permissions_and_removal(client, factory):
    _, headers, theme, _ = await catalog(client)
    _, other_headers, _ = await account(client, "다른사람", "01022222222")
    assert (await client.post("/media/v1/review-photos", content=image_bytes())).status_code == 401
    assert (
        await client.post("/media/v1/review-photos", headers=headers, content=b"not an image")
    ).status_code == 422
    result = await client.post("/media/v1/review-photos", headers=headers, content=image_bytes())
    assert result.status_code == 201, result.text
    photo = result.json()
    assert (await client.get(photo["url"])).status_code == 404  # not published yet
    body = {"theme_id": theme["id"], "rating": 4, "date": "2026-11-01", "photo_ids": [photo["id"]]}
    assert (await client.post("/review/v1", headers=other_headers, json=body)).status_code == 422
    assert (
        await client.post(
            "/review/v1", headers=headers, json={**body, "photo_ids": [photo["id"]] * 6}
        )
    ).status_code == 422
    result = await client.post("/review/v1", headers=headers, json=body)
    assert result.status_code == 201, result.text
    review = result.json()
    assert review["photos"] == [photo]
    data = await client.get(photo["url"])
    assert data.status_code == 200
    assert data.headers["content-type"] == "image/jpeg"
    with Image.open(BytesIO(data.content)) as image:
        assert image.size == (1600, 800)
        assert not image.getexif()
    # Ordinary edits preserve photos; an explicit empty list removes them.
    path = "/review/v1/" + review["id"]
    response = await client.patch(path, headers=headers, json={"content": "수정"})
    assert response.json()["photos"] == [photo]
    assert (
        await client.patch(path, headers=other_headers, json={"photo_ids": []})
    ).status_code == 403
    assert (await client.patch(path, headers=headers, json={"photo_ids": []})).json()[
        "photos"
    ] == []
    assert (await client.get(photo["url"])).status_code == 404
    await client.patch(path, headers=headers, json={"photo_ids": [photo["id"]]})
    await client.delete(path, headers=headers)
    assert (await client.get(photo["url"])).status_code == 404
    async with factory() as db:
        assert (await db.get(ReviewPhoto, UUID(photo["id"]))).review_id is None


@pytest.mark.asyncio
async def test_cleanup_keeps_published_and_recent_photos(client, factory):
    from datetime import timedelta
    from pathlib import Path

    from app.domain.models import now
    from app.jobs.cleanup_photos import cleanup
    from app.services import photos

    user, headers, theme, _ = await catalog(client)
    old = now() - timedelta(days=2)
    async with factory() as db:
        review = Review(
            user_id=UUID(user["id"]), theme_id=UUID(theme["id"]), rating=4, date=date(2026, 11, 1)
        )
        db.add(review)
        await db.flush()
        for key, attached, timestamp in [
            ("old.jpg", None, old),
            ("recent.jpg", None, now()),
            ("published.jpg", review.id, old),
        ]:
            photos.write(key, image_bytes())
            db.add(
                ReviewPhoto(
                    user_id=UUID(user["id"]),
                    review_id=attached,
                    object_key=key,
                    updated_dt=timestamp,
                )
            )
        await db.commit()
        assert await cleanup(db) == 1
        assert set(await db.scalars(select(ReviewPhoto.object_key))) == {
            "recent.jpg",
            "published.jpg",
        }
        assert {p.name for p in Path(settings.review_photo_local_dir).iterdir()} == {
            "recent.jpg",
            "published.jpg",
        }
        assert await cleanup(db) == 0
