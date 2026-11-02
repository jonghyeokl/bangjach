from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from pydantic import Json
from sqlalchemy import exists, func, or_, select
from starlette.concurrency import run_in_threadpool

from app.api.users import Page, Size
from app.core.errors import fail
from app.core.security import DB, Admin, Identity
from app.domain import responses as out
from app.domain.enums import LABELS, Genre, Region
from app.domain.models import Cafe, Friend, Review, Theme, ThemeStatistics
from app.domain.schemas import CafeCreate, ThemeCreate
from app.services import photos, views
from app.services.limits import limit
from app.services.privacy import check_visibility, friend_condition

router = APIRouter(tags=["catalog"])


@router.get("/meta/v1/enums", response_model=dict[str, list[out.EnumOption]])
async def enums():
    return {
        key: [{"value": int(v), "label": label} for v, label in zip(enum, labels)]
        for key, (enum, labels) in LABELS.items()
    }


@router.post("/cafe/v1", status_code=201, response_model=out.CafeResponse)
async def create_cafe(body: CafeCreate, db: DB, user: Admin):
    row = Cafe(**body.model_dump(mode="json"))
    db.add(row)
    await db.commit()
    return views.cafe(row)


@router.post("/theme/v1", status_code=201, response_model=out.ThemeResponse)
async def create_theme(body: ThemeCreate, db: DB, user: Admin):
    place = await db.get(Cafe, body.cafe_id)
    if not place:
        fail(404, "CAFE_NOT_FOUND", "카페를 찾을 수 없습니다.")
    data = body.model_dump(mode="json")
    data["cafe_id"] = body.cafe_id
    row = Theme(**data)
    db.add(row)
    await db.commit()
    return views.theme(row, place, None, True)


@router.post("/theme/v1/with-photo", status_code=201, response_model=out.ThemeResponse)
async def create_theme_with_photo(
    db: DB, user: Admin, data: Annotated[Json[ThemeCreate], Form()], photo: UploadFile
):
    await limit(db, "theme-photo:" + str(user.id), 30)
    place = await db.get(Cafe, data.cafe_id)
    if not place:
        fail(404, "CAFE_NOT_FOUND", "카페를 찾을 수 없습니다.")
    content = await photo.read(photos.MAX_BYTES + 1)
    if len(content) > photos.MAX_BYTES:
        fail(413, "PHOTO_TOO_LARGE", "사진 한 장은 8MB 이하여야 합니다.")
    normalized = await run_in_threadpool(photos.normalize, content)
    theme_id = uuid4()
    key = f"themes/{theme_id}.jpg"
    try:
        await run_in_threadpool(photos.write, key, normalized)
    except HTTPException:
        raise
    except Exception:
        fail(503, "PHOTO_UPLOAD_FAILED", "사진을 저장하지 못했어요. 잠시 후 다시 시도해주세요.")
    values = data.model_dump(mode="json", exclude={"image_url"})
    values["cafe_id"] = data.cafe_id
    row = Theme(
        **values,
        id=theme_id,
        image_url=f"/media/v1/theme-photos/{theme_id}",
    )
    db.add(row)
    try:
        await db.commit()
    except Exception:
        await run_in_threadpool(photos.remove, key)
        raise
    return views.theme(row, place, None, True)


@router.get("/cafe/v1", response_model=out.PageResponse[out.CafeResponse])
async def cafes(
    db: DB,
    q: str | None = None,
    region: Annotated[list[Region] | None, Query()] = None,
    page: Page = 1,
    page_size: Size = 20,
):
    query = select(Cafe)
    if q:
        query = query.where(Cafe.name.contains(q, autoescape=True))
    if region:
        query = query.where(Cafe.region.in_(region))
    return await views.paginate(db, query.order_by(Cafe.name, Cafe.id), page, page_size, views.cafe)


@router.get("/cafe/v1/{cafe_id}", response_model=out.CafeResponse)
async def cafe(cafe_id: UUID, db: DB):
    row = await db.get(Cafe, cafe_id)
    if not row:
        fail(404, "CAFE_NOT_FOUND", "카페를 찾을 수 없습니다.")
    return views.cafe(row)


def array_contains(db, column, value):
    if db.bind.dialect.name == "postgresql":
        return column.op("@>")([int(value)])
    element = func.json_each(column).table_valued("value")
    return exists(select(1).select_from(element).where(element.c.value == int(value)))


@router.get("/theme/v1", response_model=out.PageResponse[out.ThemeSummaryResponse])
async def themes(
    db: DB,
    who: Identity,
    q: Annotated[str | None, Query(max_length=100)] = None,
    region: Annotated[list[Region] | None, Query()] = None,
    genre: Annotated[list[Genre] | None, Query()] = None,
    cafe_id: UUID | None = None,
    difficulty_min: float | None = None,
    difficulty_max: float | None = None,
    horrorness_min: float | None = None,
    horrorness_max: float | None = None,
    physicality_min: float | None = None,
    physicality_max: float | None = None,
    exclude_played: bool = False,
    party_user_id: Annotated[list[UUID] | None, Query(max_length=20)] = None,
    sort: Literal["newest", "rating", "difficulty", "horrorness", "physicality"] = "newest",
    order: Literal["asc", "desc"] = "desc",
    page: Page = 1,
    page_size: Size = 20,
):
    query = views.THEME_QUERY
    if q:
        query = query.where(
            or_(Theme.name.contains(q, autoescape=True), Cafe.name.contains(q, autoescape=True))
        )
    if cafe_id:
        query = query.where(Theme.cafe_id == cafe_id)
    if region:
        query = query.where(Cafe.region.in_(region))
    if genre:
        query = query.where(
            or_(*[array_contains(db, ThemeStatistics.most_genre_list, g) for g in genre])
        )
    for field, low, high in [
        ("difficulty", difficulty_min, difficulty_max),
        ("horrorness", horrorness_min, horrorness_max),
        ("physicality", physicality_min, physicality_max),
    ]:
        for value in (low, high):
            if value is not None and (not 1 <= value <= 5 or Decimal(str(value)) % Decimal("0.5")):
                fail(422, "INVALID_RANGE", "필터는 1~5, 0.5 간격입니다.")
        if low is not None and high is not None and low > high:
            fail(422, "INVALID_RANGE", "최솟값은 최댓값 이하여야 합니다.")
        col = getattr(ThemeStatistics, "avg_" + field)
        if low is not None:
            query = query.where(col >= low)
        if high is not None:
            query = query.where(col <= high)
    if party_user_id and not exclude_played:
        fail(422, "INVALID_PARTY", "일행 필터는 안 한 테마 검색에서 사용하세요.")
    if exclude_played:
        if not who:
            fail(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        ids = set(party_user_id or []) | {who[0].id}
        for target in ids:
            if target != who[0].id and not await db.scalar(
                select(Friend.id).where(friend_condition(who[0].id, target))
            ):
                fail(403, "FRIENDS_ONLY", "일행은 친구 목록에서만 선택할 수 있습니다.")
            await check_visibility(db, who[0].id, target, "party_search_publicity")
        query = query.where(
            ~exists(select(Review.id).where(Review.theme_id == Theme.id, Review.user_id.in_(ids)))
        )
    col = (
        Theme.created_dt
        if sort == "newest"
        else ThemeStatistics.normalized_rating
        if sort == "rating"
        else getattr(ThemeStatistics, "avg_" + sort)
    )
    query = query.order_by((col.asc() if order == "asc" else col.desc()).nulls_last(), Theme.id)
    return await views.paginate(db, query, page, page_size, views.theme)


@router.get("/theme/v1/{theme_id}", response_model=out.ThemeResponse)
async def detail(theme_id: UUID, db: DB):
    row = (await db.execute(views.THEME_QUERY.where(Theme.id == theme_id))).first()
    if not row:
        fail(404, "THEME_NOT_FOUND", "테마를 찾을 수 없습니다.")
    return views.theme(*row, detail=True)


@router.get("/theme/v1/{theme_id}/statistics", response_model=out.ThemeStatisticsResponse)
async def statistics(theme_id: UUID, db: DB):
    if not await db.get(Theme, theme_id):
        fail(404, "THEME_NOT_FOUND", "테마를 찾을 수 없습니다.")
    return views.stats(
        await db.scalar(select(ThemeStatistics).where(ThemeStatistics.theme_id == theme_id))
    )
