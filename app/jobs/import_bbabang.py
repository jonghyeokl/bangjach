"""Import an exported bbabang catalog. Preview by default; --apply writes atomically."""

import argparse
import asyncio
import json
import unicodedata
import warnings
from io import BytesIO
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from PIL import Image, ImageOps
from pydantic import ValidationError
from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.domain.models import Cafe, Theme
from app.domain.schemas import CafeCreate, ThemeCreate
from app.services import photos

REGIONS = {
    1: ["서울", "서울특별시"],
    2: ["경기", "경기도"],
    3: ["인천", "인천광역시"],
    4: [
        "충청",
        "충북",
        "충남",
        "충청북도",
        "충청남도",
        "대전",
        "대전광역시",
        "세종",
        "세종특별자치시",
    ],
    5: ["강원", "강원도", "강원특별자치도"],
    6: [
        "경상",
        "경북",
        "경남",
        "경상북도",
        "경상남도",
        "부산",
        "부산광역시",
        "대구",
        "대구광역시",
        "울산",
        "울산광역시",
    ],
    7: ["전라", "전북", "전남", "전라북도", "전라남도", "전북특별자치도", "광주", "광주광역시"],
    8: ["제주", "제주도", "제주특별자치도"],
}
REGION_BY_NAME = {name: region for region, names in REGIONS.items() for name in names}
SOURCE = "https://bbabang.net/#home"
IMPORT_COUNT = 100


def stable_id(kind, value):
    return uuid5(NAMESPACE_URL, f"https://bbabang.net/bangjach-import/{kind}/{value}")


def clean(value):
    return unicodedata.normalize("NFC", value.strip()) if isinstance(value, str) else ""


def read_export(file):
    data = json.loads(file.read_text(encoding="utf-8"))
    if (
        data.get("schema_version") != 1
        or data.get("source") != SOURCE
        or data.get("count") != IMPORT_COUNT
        or len(data.get("themes", [])) != IMPORT_COUNT
        or data.get("request", {}).get("sort") != ["recommendTotalRating:desc"]
        or set(data.get("request", {}).get("filter", []))
        != {"isopen != false", "store_isopen != false"}
        or data.get("request", {}).get("query") != ""
    ):
        raise ValueError(f"지정한 조건의 빠방 테마 {IMPORT_COUNT}개 파일이 아닙니다.")
    ids = [row.get("source_id") for row in data["themes"]]
    if any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != IMPORT_COUNT:
        raise ValueError("원본 테마 ID가 없거나 중복되었습니다.")
    if [row.get("rank") for row in data["themes"]] != list(range(1, IMPORT_COUNT + 1)):
        raise ValueError("원본 순위가 올바르지 않습니다.")
    return data


def cafe_payload(row):
    source = row.get("cafe") or {}
    address = clean(source.get("address"))
    label = clean(source.get("region_label"))
    region = REGION_BY_NAME.get(label)
    if region is None and address:
        region = REGION_BY_NAME.get(address.split()[0])
    phone = clean(source.get("phone_number"))
    if not any(char.isdigit() for char in phone):
        phone = ""
    return CafeCreate(
        name=clean(row.get("cafe_name")),
        region=region,
        address=address,
        phone_number=phone,
        website=source.get("website") or row.get("website"),
    )


def normalize_import_photo(path):
    if path.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("원본 사진이 12MB를 초과합니다.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as original:
            if original.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("JPEG/PNG/WebP 사진만 지원합니다.")
            if original.width * original.height > 64_000_000:
                raise ValueError("원본 사진이 6,400만 화소를 초과합니다.")
            # Large imported posters are downsampled before the normal upload validation.
            # The public upload API's 25 MP limit is unchanged.
            original.draft("RGB", (1600, 1600))
            image = ImageOps.exif_transpose(original)
            image.thumbnail((1600, 1600))
            output = BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=85)
    return photos.normalize(output.getvalue())


async def plan(db, data):
    new_cafes, new_themes, skipped, errors = [], [], [], []
    cafes = {}
    for row in data["themes"]:
        name = clean(row.get("cafe_name"))
        if not name:
            errors.append(f"{row['source_id']}: 카페명 없음")
            continue
        cafe = cafes.get(name)
        if cafe is None:
            matches = (await db.scalars(select(Cafe).where(Cafe.name == name))).all()
            if len(matches) > 1:
                errors.append(f"{name}: 같은 이름의 카페가 여러 개입니다. 수동 매칭이 필요합니다.")
                continue
            if matches:
                cafe = matches[0]
                source_address = clean((row.get("cafe") or {}).get("address"))
                if source_address and clean(cafe.address) != source_address:
                    errors.append(f"{name}: 기존 카페와 주소가 다릅니다. 수동 확인이 필요합니다.")
                    continue
            else:
                try:
                    values = cafe_payload(row).model_dump(mode="json")
                except ValidationError as exc:
                    fields = ", ".join(str(e["loc"][0]) for e in exc.errors())
                    errors.append(f"{name}: 카페 필수 정보 확인 필요 ({fields})")
                    continue
                cafe = Cafe(id=stable_id("cafe", name), **values)
                new_cafes.append(cafe)
            cafes[name] = cafe
        # Different source rows for one cafe must not disagree on its address.
        source_address = clean((row.get("cafe") or {}).get("address"))
        if source_address and clean(cafe.address) != source_address:
            errors.append(f"{name}: 원본 카페 주소가 서로 다릅니다.")
            continue
        theme_id = stable_id("theme", row["source_id"])
        existing = await db.get(Theme, theme_id)
        theme_name = clean(row.get("theme_name"))
        if existing:
            if existing.cafe_id != cafe.id:
                errors.append(f"{theme_name}: 이미 등록된 원본 ID의 카페가 다릅니다.")
            else:
                skipped.append({"source_id": row["source_id"], "id": str(existing.id)})
            continue
        matches = (
            await db.scalars(
                select(Theme).where(Theme.cafe_id == cafe.id, Theme.name == theme_name)
            )
        ).all()
        if len(matches) > 1:
            errors.append(f"{name} / {theme_name}: 같은 이름의 테마가 여러 개입니다.")
            continue
        if matches:
            skipped.append({"source_id": row["source_id"], "id": str(matches[0].id)})
            continue
        try:
            values = ThemeCreate(
                name=theme_name,
                cafe_id=cafe.id,
                description=row.get("description"),
                length=row.get("length_minutes"),
                website=row.get("website"),
            ).model_dump(mode="json", exclude={"image_url", "cafe_id"})
        except ValidationError as exc:
            fields = ", ".join(str(e["loc"][0]) for e in exc.errors())
            errors.append(f"{theme_name}: 테마 정보 확인 필요 ({fields})")
            continue
        new_themes.append((row, Theme(id=theme_id, cafe_id=cafe.id, **values)))
    used = {theme.cafe_id for _, theme in new_themes}
    new_cafes = [cafe for cafe in new_cafes if cafe.id in used]
    return new_cafes, new_themes, skipped, sorted(set(errors))


async def import_catalog(db, data, root, *, apply=False):
    if db.bind.dialect.name == "postgresql":
        # Serialize importer runs, including a concurrent rerun of the same source IDs.
        await db.execute(text("SELECT pg_advisory_xact_lock(726104113)"))
    cafes, themes, skipped, errors = await plan(db, data)
    report = {
        "mode": "apply" if apply else "preview",
        "committed": False,
        "new_cafes": len(cafes),
        "new_themes": len(themes),
        "skipped": len(skipped),
        "errors": errors,
        "theme_ids": list(skipped),
    }
    if errors:
        await db.rollback()
        return report
    prepared = []
    for row, theme in themes:
        try:
            relative = row.get("image_file")
            if not relative:
                raise ValueError("사진 파일이 없습니다. 사진 다운로드를 먼저 완료해주세요.")
            photo_path = (root / relative).resolve()
            if not photo_path.is_relative_to(root.resolve()):
                raise ValueError("사진 경로가 수집 폴더 밖을 가리킵니다.")
            content = await run_in_threadpool(normalize_import_photo, photo_path)
            prepared.append((row, theme, content))
        except Exception as exc:
            # Do not echo DB URLs, authentication headers, or third-party request details.
            errors.append(f"{row['theme_name']}: 사진 처리 실패 ({type(exc).__name__})")
    if errors or not apply:
        await db.rollback()
        return report
    written = []
    try:
        db.add_all(cafes)
        await db.flush()
        for row, theme, content in prepared:
            key = f"themes/{theme.id}.jpg"
            written.append(key)
            await run_in_threadpool(photos.write, key, content)
            theme.image_url = f"/media/v1/theme-photos/{theme.id}"
            db.add(theme)
            report["theme_ids"].append({"source_id": row["source_id"], "id": str(theme.id)})
        await db.commit()
        report["committed"] = True
    except Exception as exc:
        await db.rollback()
        report["errors"].append(f"등록 실패, DB 변경을 취소했습니다 ({type(exc).__name__}).")
        for key in written:
            try:
                await run_in_threadpool(photos.remove, key)
            except Exception:
                report["errors"].append(f"저장소 정리 필요: {key}")
        report["theme_ids"] = skipped
    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="사진을 내려받은 themes.json")
    parser.add_argument("--apply", action="store_true", help="검증 후 실제 DB에 등록")
    parser.add_argument("--photo-bucket", help="서비스와 동일한 비공개 Cloud Storage 버킷")
    parser.add_argument("--local-photos", action="store_true", help="개발 DB의 로컬 사진 폴더 사용")
    args = parser.parse_args()
    data = read_export(args.input)
    if args.photo_bucket:
        settings.review_photo_bucket = args.photo_bucket
    if args.apply and not settings.review_photo_bucket:
        if not args.local_photos or settings.environment == "production":
            raise ValueError("DB 등록 시 --photo-bucket 또는 개발용 --local-photos를 지정해주세요.")
    async with SessionLocal() as db:
        report = await import_catalog(db, data, args.input.parent, apply=args.apply)
    destination = args.input.parent / "import-report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"결과: {destination}")
    await engine.dispose()
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except (ValueError, OSError) as exc:
        print(f"입력/설정 오류: {exc}")
        raise SystemExit(1) from None
    except Exception as exc:
        print(
            f"등록 작업을 완료하지 못했습니다 ({type(exc).__name__}). "
            "DB 연결과 저장소 권한을 확인하세요."
        )
        raise SystemExit(1) from None
