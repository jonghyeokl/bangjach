import asyncio
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from conftest import account, catalog
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.domain.models import Review, User
from app.jobs.statistics import recalculate
from app.services import keywords

pytestmark = pytest.mark.asyncio


async def test_auth_uniqueness_rotation_and_revocation(client):
    user, headers, tokens = await account(client)
    assert "password" not in str(user)
    assert (await client.get("/user/v1/me", headers=headers)).json()["id"] == user["id"]
    assert (await client.get("/user/v1/me")).status_code == 401
    duplicate = await client.post(
        "/user/v1/sign-up",
        json={"phone_number": "01022222222", "password": "test-password", "name": " 플레이어 "},
    )
    assert duplicate.status_code == 409
    bad = await client.post(
        "/user/v1/log-in", json={"phone_number": "01011111111", "password": "wrong"}
    )
    assert bad.status_code == 401 and "wrong" not in bad.text
    r = await client.post("/user/v1/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert (
        await client.post("/user/v1/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 401
    new_headers = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert (await client.post("/user/v1/log-out", headers=new_headers)).status_code == 204
    assert (await client.get("/user/v1/me", headers=headers)).status_code == 401
    assert (
        await client.post("/user/v1/refresh", json={"refresh_token": r.json()["refresh_token"]})
    ).status_code == 401


async def test_review_validation_crud_and_calendar(client):
    user, headers, theme, _ = await catalog(client)
    body = {"theme_id": theme["id"], "rating": 4.5, "date": "2026-12-31"}
    for bad in [
        {"date": None},
        {"date": "2026-02-30"},
        {"rating": 1.49},
        {"rating": True},
        {"rating": "4.5"},
        {"genre_list": [99]},
        {"people_size": 0},
        {"review_keyword_list": [1]},
    ]:
        r = await client.post("/review/v1", json={**body, **bad}, headers=headers)
        assert r.status_code == 422, (bad, r.text)
    assert (
        await client.post(
            "/review/v1", json={"theme_id": theme["id"], "rating": 4}, headers=headers
        )
    ).status_code == 422
    result = await client.post(
        "/review/v1", json={**body, "genre_list": [1, 1, 3]}, headers=headers
    )
    assert result.status_code == 201, result.text
    review = result.json()
    assert review["rating"] == 4.5 and review["genre_list"] == [1, 3]
    assert review["keyword_analysis_status"] == 1
    assert (await client.post("/review/v1", json=body, headers=headers)).status_code == 409
    public = await client.get(f"/review/v1/{review['id']}")
    assert public.status_code == 200 and "phone_number" not in public.text
    path = f"/user/v1/{user['id']}/calendar"
    assert (
        len((await client.get(path, params={"month": "2026-12"}, headers=headers)).json()["items"])
        == 1
    )
    assert (await client.get(path, params={"month": "2026-13"}, headers=headers)).status_code == 422
    _, other, _ = await account(client, "다른 사람", "01022222222")
    assert (
        await client.patch(f"/review/v1/{review['id']}", json={"rating": 3}, headers=other)
    ).status_code == 403
    assert (await client.delete(f"/review/v1/{review['id']}", headers=other)).status_code == 403
    for patch in [
        {},
        {"date": None},
        {"rating": None},
        {"genre_list": None},
        {"theme_id": theme["id"]},
    ]:
        assert (
            await client.patch(f"/review/v1/{review['id']}", json=patch, headers=headers)
        ).status_code == 422
    result = await client.patch(
        f"/review/v1/{review['id']}",
        json={"date": "2027-01-01", "content": "연출이 별로였다"},
        headers=headers,
    )
    assert result.status_code == 200, result.text
    assert result.json()["keyword_analysis_status"] == 3
    assert result.json()["genre_list"] == [1, 3]
    assert (await client.get(path, params={"month": "2026-12"}, headers=headers)).json()[
        "items"
    ] == []
    assert (
        len((await client.get(path, params={"month": "2027-01"}, headers=headers)).json()["items"])
        == 1
    )
    assert (await client.get("/theme/v1?exclude_played=true", headers=headers)).json()["total"] == 0
    assert (await client.delete(f"/review/v1/{review['id']}", headers=headers)).status_code == 204
    assert (await client.get("/theme/v1?exclude_played=true", headers=headers)).json()["total"] == 1


async def test_friend_permissions_and_lifecycle(client):
    owner, oh, theme, _ = await catalog(client)
    friend, fh, _ = await account(client, "친구", "01022222222")
    outsider, xh, _ = await account(client, "타인", "01033333333")
    path = f"/user/v1/{owner['id']}/calendar?month=2026-11"
    assert (await client.get(path, headers=fh)).status_code == 403
    s = (await client.get("/user/v1/me/settings", headers=oh)).json()
    assert s["calendar_publicity"] == s["party_search_publicity"] == 2
    request = await client.post(
        "/friend-request/v1", headers=fh, json={"requested_user_name": owner["name"]}
    )
    assert request.status_code == 201
    rid = request.json()["id"]
    assert (
        await client.post(
            "/friend-request/v1", headers=oh, json={"requested_user_name": friend["name"]}
        )
    ).status_code == 409
    assert (await client.post(f"/friend-request/v1/{rid}/accept", headers=xh)).status_code == 403
    assert (await client.post(f"/friend-request/v1/{rid}/accept", headers=fh)).status_code == 403
    accepted = await client.post(f"/friend-request/v1/{rid}/accept", headers=oh)
    assert accepted.status_code == 200
    assert (await client.get(path, headers=fh)).status_code == 200
    assert (await client.get("/friend-request/v1?direction=sent", headers=fh)).json()["total"] == 0
    await client.post(
        "/review/v1", headers=oh, json={"theme_id": theme["id"], "rating": 5, "date": "2026-11-01"}
    )
    params = {"exclude_played": "true", "party_user_id": owner["id"]}
    assert (await client.get("/theme/v1", params=params, headers=fh)).json()["total"] == 0
    assert (await client.get("/theme/v1", params=params, headers=xh)).status_code == 403
    await client.patch("/user/v1/me/settings", json={"calendar_publicity": 1}, headers=oh)
    assert (await client.get(path, headers=fh)).status_code == 403
    assert (await client.get(path, headers=oh)).status_code == 200
    await client.patch("/user/v1/me/settings", json={"calendar_publicity": 3}, headers=oh)
    assert (await client.get(path, headers=xh)).status_code == 200
    await client.patch("/user/v1/me/settings", json={"calendar_publicity": 2}, headers=oh)
    fid = accepted.json()["id"]
    assert (await client.delete(f"/friend/v1/{fid}", headers=xh)).status_code == 403
    assert (await client.delete(f"/friend/v1/{fid}", headers=fh)).status_code == 204
    assert (await client.get(path, headers=fh)).status_code == 403
    assert (await client.get("/theme/v1", params=params, headers=fh)).status_code == 403
    for method in ("reject", "cancel"):
        r = await client.post(
            "/friend-request/v1", headers=fh, json={"requested_user_name": owner["name"]}
        )
        rid = r.json()["id"]
        result = (
            await client.post(f"/friend-request/v1/{rid}/reject", headers=oh)
            if method == "reject"
            else await client.delete(f"/friend-request/v1/{rid}", headers=fh)
        )
        assert result.status_code == 204


async def test_statistics_all_themes_and_null_filters(client, factory):
    _, headers, theme, cafe = await catalog(client)
    t2 = (
        await client.post(
            "/theme/v1",
            headers=headers,
            json={"name": "두 번째", "description": "", "cafe_id": cafe["id"], "length": 70},
        )
    ).json()
    auths = [headers]
    for i in range(2):
        _, h, _ = await account(client, f"통계{i}", f"0102222222{i}")
        auths.append(h)
    ids = []
    for h, rating, genres in zip(auths, [5, 3, 4], [[1, 2], [1], [2]]):
        r = await client.post(
            "/review/v1",
            headers=h,
            json={
                "theme_id": theme["id"],
                "rating": rating,
                "date": "2026-11-01",
                "genre_list": genres,
                "difficulty": 3,
            },
        )
        ids.append(r.json()["id"])
    extra = await client.post(
        "/review/v1",
        headers=headers,
        json={"theme_id": t2["id"], "rating": 1, "date": "2026-11-01"},
    )
    async with factory() as db:
        assert await recalculate(db) == 2
    stat = (await client.get(f"/theme/v1/{theme['id']}/statistics")).json()
    assert stat["avg_rating"] == 4 and stat["most_genre_list"] == [1, 2]
    assert stat["avg_horrorness"] is None and stat["avg_difficulty"] == 3
    # mu=3.25. User A's mean=3; B=3; C=4. Biases -1/24, -1/44, 3/44.
    expected = ((5 + 1 / 24) + (3 + 1 / 44) + (4 - 3 / 44)) / 3
    assert stat["normalized_rating"] == pytest.approx(expected)
    assert (await client.get("/theme/v1?genre=1")).json()["total"] == 1
    assert (await client.get("/theme/v1?horrorness_min=1")).json()["total"] == 0
    assert (await client.get("/theme/v1?difficulty_min=1.49")).status_code == 422
    assert (await client.get("/theme/v1?difficulty_min=5&difficulty_max=1")).status_code == 422
    assert (await client.get("/theme/v1?sort=rating&order=desc")).json()["items"][0]["id"] == theme[
        "id"
    ]
    await client.patch(f"/review/v1/{extra.json()['id']}", headers=headers, json={"rating": 5})
    async with factory() as db:
        await recalculate(db)
    updated = (await client.get(f"/theme/v1/{theme['id']}/statistics")).json()
    assert updated["normalized_rating"] != stat["normalized_rating"]
    await client.delete(f"/review/v1/{ids[-1]}", headers=auths[-1])
    async with factory() as db:
        await recalculate(db)
    stat = (await client.get(f"/theme/v1/{theme['id']}/statistics")).json()
    assert stat["avg_rating"] is None and stat["most_genre_list"] is None
    for rid, h in zip(ids[:2], auths[:2]):
        await client.delete(f"/review/v1/{rid}", headers=h)
    async with factory() as db:
        await recalculate(db)
    assert (await client.get(f"/theme/v1/{theme['id']}/statistics")).json()["review_count"] == 0


async def test_keyword_filter_failure_and_edit_race(client, monkeypatch):
    _, headers, theme, _ = await catalog(client)

    async def analysis(content):
        return {
            "review_keyword_list": [1, 2] if content else [],
            "keyword_analysis_status": 2 if content else 1,
        }

    monkeypatch.setattr(keywords, "analyze", analysis)
    r = await client.post(
        "/review/v1",
        headers=headers,
        json={
            "theme_id": theme["id"],
            "rating": 4,
            "date": "2026-11-01",
            "content": "인테리어와 연출",
            "people_size": 2,
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert (
        await client.get(f"/review/v1?theme_id={theme['id']}&keyword=1&keyword=3&keyword_match=all")
    ).json()["total"] == 0
    assert (await client.get(f"/review/v1?theme_id={theme['id']}&keyword=1&keyword=3")).json()[
        "total"
    ] == 1
    chips = (await client.get(f"/theme/v1/{theme['id']}/review-keywords?people_size=2")).json()
    assert chips["items"][0]["review_count"] == 1
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(content):
        started.set()
        await release.wait()
        return await analysis(content)

    monkeypatch.setattr(keywords, "analyze", slow)
    editing = asyncio.create_task(
        client.patch(f"/review/v1/{rid}", headers=headers, json={"content": "느린 분석"})
    )
    await started.wait()
    assert (
        await client.patch(f"/review/v1/{rid}", headers=headers, json={"rating": 5})
    ).status_code == 200
    release.set()
    assert (await editing).status_code == 409
    monkeypatch.setattr(keywords, "analyze", analysis)
    r = await client.patch(f"/review/v1/{rid}", headers=headers, json={"content": None})
    assert r.json()["review_keyword_list"] == [] and r.json()["keyword_analysis_status"] == 1


async def test_llm_contract_and_malformed_response(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    real_client = httpx.AsyncClient
    for content, status, codes in [
        ('{"keywords":[2,1,2]}', 2, [1, 2]),
        ('{"keywords":[]}', 2, []),
        ('{"keywords":[true]}', 3, []),
        ('{"keywords":[99]}', 3, []),
        ("bad-json", 3, []),
    ]:

        def handler(request):
            assert request.url.path == "/v1/chat/completions"
            assert "phone_number" not in request.content.decode()
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        monkeypatch.setattr(
            keywords.httpx,
            "AsyncClient",
            lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
        )
        result = await keywords.analyze("연출이 별로였어요")
        assert (
            result["keyword_analysis_status"] == status and result["review_keyword_list"] == codes
        )
    assert (await keywords.analyze(None))["keyword_analysis_status"] == 1


async def test_admin_and_rate_limits(client):
    user, headers, _ = await account(client)
    r = await client.post(
        "/cafe/v1",
        headers=headers,
        json={"name": "없음", "phone_number": "02", "region": 1, "address": "서울"},
    )
    assert r.status_code == 403
    settings.rate_limit_enabled = True
    for _ in range(10):
        r = await client.post(
            "/user/v1/log-in", json={"phone_number": user["phone_number"], "password": "wrong"}
        )
        assert r.status_code == 401
    assert (
        await client.post(
            "/user/v1/log-in", json={"phone_number": user["phone_number"], "password": "wrong"}
        )
    ).status_code == 429


async def test_postgres_constraints_and_concurrent_requests(client, factory):
    async with factory() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL row locks and array constraints")
    owner, oh, theme, _ = await catalog(client)
    friend, fh, tokens = await account(client, "동시 요청", "01022222222")
    replies = await asyncio.gather(
        client.post("/friend-request/v1", headers=oh, json={"requested_user_name": friend["name"]}),
        client.post("/friend-request/v1", headers=fh, json={"requested_user_name": owner["name"]}),
    )
    assert sorted(r.status_code for r in replies) == [201, 409]
    results = await asyncio.gather(
        *[
            client.post("/user/v1/refresh", json={"refresh_token": tokens["refresh_token"]})
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in results) == [200, 401]
    results = await asyncio.gather(
        *[
            client.post(
                "/review/v1",
                headers=oh,
                json={"theme_id": theme["id"], "rating": 4, "date": "2026-11-01"},
            )
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in results) == [201, 409]
    rid = UUID(next(r for r in results if r.status_code == 201).json()["id"])
    for change in [
        {"date": None},
        {"rating": Decimal("1.2")},
        {"genre_list": [1, 1]},
        {"genre_list": [99]},
        {"review_keyword_list": [None]},
    ]:
        async with factory() as db:
            with pytest.raises(IntegrityError):
                await db.execute(update(Review).where(Review.id == rid).values(**change))
                await db.commit()
    async with factory() as db:
        hashed = await db.scalar(select(User.password_hash).where(User.id == UUID(owner["id"])))
        assert hashed.startswith("$argon2id$")
        dtype = await db.scalar(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='review' AND column_name='genre_list'"
            )
        )
        assert dtype == "ARRAY"


async def test_admin_flag_tracks_server_allowlist(client):
    user, headers, session = await account(client, "관리자권한검사")
    assert user["is_admin"] is False
    settings.admin_user_ids = [user["id"]]
    assert (await client.get("/user/v1/me", headers=headers)).json()["is_admin"] is True
    login = await client.post(
        "/user/v1/log-in",
        json={
            "phone_number": user["phone_number"],
            "password": "test-password",
        },
    )
    assert login.json()["user"]["is_admin"] is True
    refreshed = await client.post(
        "/user/v1/refresh", json={"refresh_token": session["refresh_token"]}
    )
    assert refreshed.json()["user"]["is_admin"] is True
    settings.admin_user_ids = []
    assert (await client.get("/user/v1/me", headers=headers)).json()["is_admin"] is False
    assert (
        await client.post(
            "/cafe/v1",
            headers=headers,
            json={
                "name": "권한 회수 후",
                "phone_number": "02",
                "region": 1,
                "address": "서울",
            },
        )
    ).status_code == 403


async def test_party_search_only_returns_allowed_friends(client):
    owner, headers, _, _ = await catalog(client)
    friend, fh, _ = await account(client, "일행친구", "01022222222")
    outsider, xh, _ = await account(client, "일행타인", "01033333333")
    # Even a stranger with public party visibility cannot be searched or supplied by ID.
    await client.patch("/user/v1/me/settings", headers=xh, json={"party_search_publicity": 3})
    request = await client.post(
        "/friend-request/v1", headers=headers, json={"requested_user_name": friend["name"]}
    )
    await client.post(f"/friend-request/v1/{request.json()['id']}/accept", headers=fh)
    params = {"q": "일행", "purpose": "party"}
    response = await client.get("/user/v1/search", headers=headers, params=params)
    assert [u["id"] for u in response.json()["items"]] == [friend["id"]]
    assert (
        await client.get(
            "/theme/v1",
            headers=headers,
            params={"exclude_played": True, "party_user_id": outsider["id"]},
        )
    ).status_code == 403
    # Friend discovery is intentionally separate and still finds non-friends.
    assert (
        await client.get(
            "/user/v1/search", headers=headers, params={"q": "일행", "purpose": "friend"}
        )
    ).json()["total"] == 2
    await client.patch("/user/v1/me/settings", headers=fh, json={"party_search_publicity": 1})
    assert (await client.get("/user/v1/search", headers=headers, params=params)).json()[
        "total"
    ] == 0
    assert (
        await client.get(
            "/theme/v1",
            headers=headers,
            params={"exclude_played": True, "party_user_id": friend["id"]},
        )
    ).status_code == 403
