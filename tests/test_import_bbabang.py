import asyncio
import json
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.domain.models import Cafe, Theme
from app.jobs.import_bbabang import import_catalog, normalize_import_photo, read_export
from app.services import photos


def test_read_export_requires_100_unique_ranked_themes(tmp_path):
    data = {
        "schema_version": 1,
        "source": "https://bbabang.net/#home",
        "count": 100,
        "request": {
            "sort": ["recommendTotalRating:desc"],
            "filter": ["isopen != false", "store_isopen != false"],
            "query": "",
        },
        "themes": [{"source_id": i, "rank": i} for i in range(1, 101)],
    }
    file = tmp_path / "themes.json"

    def read():
        file.write_text(json.dumps(data), encoding="utf-8")
        return read_export(file)

    assert read() == data
    last = data["themes"].pop()
    data["count"] = 99
    with pytest.raises(ValueError, match="100개"):
        read()
    data["count"] = 100
    data["themes"].append(last)
    last["source_id"] = 1
    with pytest.raises(ValueError, match="중복"):
        read()
    last["source_id"] = 100
    last["rank"] = 99
    with pytest.raises(ValueError, match="순위"):
        read()


def source(tmp_path):
    image = tmp_path / "poster.png"
    Image.new("RGB", (1800, 900), "green").save(image)
    return {
        "themes": [
            {
                "source_id": index,
                "theme_name": f"수입테마{index}",
                "cafe_name": "가상카페 강남점",
                "description": "줄바꿈\n소개",
                "length_minutes": 75,
                "website": "https://example.com/",
                "image_file": image.name,
                "cafe": {
                    "region_label": "서울",
                    "address": "서울특별시 강남구 가상주소",
                    "phone_number": "0200000000",
                    "website": "https://example.com/",
                },
            }
            for index in (101, 102)
        ]
    }


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "review_photo_bucket", "")
    monkeypatch.setattr(settings, "review_photo_local_dir", str(tmp_path / "storage"))


async def counts(db):
    return [await db.scalar(select(func.count()).select_from(model)) for model in (Cafe, Theme)]


@pytest.mark.asyncio
async def test_preview_import_rerun_and_public_photo(client, factory, tmp_path):
    data = source(tmp_path)
    async with factory() as db:
        report = await import_catalog(db, data, tmp_path)
        assert not report["committed"] and report["new_cafes"] == 1 and report["new_themes"] == 2
        assert await counts(db) == [0, 0]
        assert not (tmp_path / "storage").exists()
    async with factory() as db:
        report = await import_catalog(db, data, tmp_path, apply=True)
        assert report["committed"] and not report["errors"]
        assert await counts(db) == [1, 2]
        row = await db.scalar(select(Theme).order_by(Theme.name))
        assert row.description == "줄바꿈\n소개"
        url = row.image_url
        row.description = "사용자가 수정한 소개"
        await db.commit()
    photo = await client.get(url)
    assert photo.status_code == 200
    with Image.open(BytesIO(photo.content)) as image:
        assert image.size == (1600, 800)
    async with factory() as db:
        again = await import_catalog(db, data, tmp_path, apply=True)
        assert again["new_cafes"] == again["new_themes"] == 0
        assert again["skipped"] == 2
        assert await counts(db) == [1, 2]
        assert (
            await db.scalar(select(Theme).order_by(Theme.name))
        ).description == "사용자가 수정한 소개"


@pytest.mark.asyncio
async def test_missing_metadata_and_bad_photos_leave_no_partial_rows(factory, tmp_path):
    data = source(tmp_path)
    data["themes"][0]["cafe"].pop("phone_number")
    async with factory() as db:
        report = await import_catalog(db, data, tmp_path, apply=True)
        assert report["errors"] and not report["committed"]
        assert await counts(db) == [0, 0]
    data = source(tmp_path)
    data["themes"][1]["image_file"] = "../outside.png"
    async with factory() as db:
        report = await import_catalog(db, data, tmp_path, apply=True)
        assert report["errors"] and not report["committed"]
        assert await counts(db) == [0, 0]
        assert not (tmp_path / "storage").exists()


@pytest.mark.asyncio
async def test_storage_failure_rolls_back_cafes_themes_and_photos(factory, tmp_path, monkeypatch):
    data = source(tmp_path)
    original = photos.write
    calls = 0

    def failing_write(key, content):
        nonlocal calls
        calls += 1
        original(key, content)
        if calls == 2:
            raise OSError("simulated failure after upload")

    monkeypatch.setattr(photos, "write", failing_write)
    async with factory() as db:
        report = await import_catalog(db, data, tmp_path, apply=True)
        assert report["errors"] and not report["committed"]
        assert report["theme_ids"] == []
        assert await counts(db) == [0, 0]
    assert not list((tmp_path / "storage").rglob("*.jpg"))


@pytest.mark.asyncio
async def test_conflicting_existing_cafe_is_not_merged(factory, tmp_path):
    data = source(tmp_path)
    async with factory() as db:
        db.add(
            Cafe(name="가상카페 강남점", address="다른 주소", region=1, phone_number="0200000000")
        )
        await db.commit()
        report = await import_catalog(db, data, tmp_path, apply=True)
        assert report["errors"] and not report["committed"]
        assert await counts(db) == [1, 0]


def test_large_poster_is_resized_without_changing_api_limits(tmp_path):
    file = tmp_path / "large.jpg"
    Image.new("RGB", (7100, 7100), "blue").save(file)
    content = normalize_import_photo(file)
    with Image.open(BytesIO(content)) as image:
        assert image.size == (1600, 1600)
        assert not image.getexif()


@pytest.mark.asyncio
async def test_concurrent_postgres_imports_do_not_duplicate(factory, tmp_path):
    data = source(tmp_path)
    async with factory() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("PostgreSQL advisory lock test")

    async def run():
        async with factory() as db:
            return await import_catalog(db, data, tmp_path, apply=True)

    results = await asyncio.gather(run(), run())
    assert all(result["committed"] for result in results)
    assert sorted(result["new_themes"] for result in results) == [0, 2]
    async with factory() as db:
        assert await counts(db) == [1, 2]
