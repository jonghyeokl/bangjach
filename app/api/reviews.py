from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import and_, func, or_, select, update

from app.api.catalog import array_contains
from app.api.users import Page, Size
from app.core.errors import fail
from app.core.security import DB, CurrentUser
from app.domain import responses as out
from app.domain.enums import LABELS, ReviewKeyword
from app.domain.models import Friend, Review, Theme, now
from app.domain.schemas import ReviewCreate, ReviewPatch
from app.services import keywords, photos, views
from app.services.limits import limit
from app.services.privacy import friend_condition

router = APIRouter(tags=["reviews"])


@router.get("/feed/v1", response_model=out.PageResponse[out.ReviewResponse])
async def feed(db: DB, user: CurrentUser, page: Page = 1, page_size: Size = 20):
    friends = select(Friend.id).where(friend_condition(user.id, Review.user_id)).exists()
    query = views.REVIEW_QUERY.where(friends, Review.user_id != user.id).order_by(
        Review.created_dt.desc(), Review.id.desc()
    )
    return await views.paginate(db, query, page, page_size, views.review)


async def get_review(db, review_id):
    row = (await db.execute(views.REVIEW_QUERY.where(Review.id == review_id))).first()
    if not row:
        fail(404, "REVIEW_NOT_FOUND", "리뷰를 찾을 수 없습니다.")
    return views.review(*row)


@router.post("/review/v1", status_code=201, response_model=out.ReviewResponse)
async def create(body: ReviewCreate, db: DB, user: CurrentUser):
    await limit(db, "review:" + str(user.id), 10)
    theme = await db.get(Theme, body.theme_id)
    if not theme:
        fail(404, "THEME_NOT_FOUND", "테마를 찾을 수 없습니다.")
    if body.played_time is not None and body.played_time > theme.length * 60:
        fail(422, "INVALID_PLAYED_TIME", "플레이 시간이 테마 전체 시간보다 길 수 없습니다.")
    if await db.scalar(
        select(Review.id).where(Review.user_id == user.id, Review.theme_id == body.theme_id)
    ):
        fail(409, "REVIEW_EXISTS", "이미 작성한 리뷰가 있습니다. 기존 리뷰를 수정하세요.")
    uid = user.id
    await db.rollback()
    analysis = await keywords.analyze(body.content)
    data = body.model_dump()
    photo_ids = data.pop("photo_ids")
    row = Review(user_id=uid, **data, **analysis)
    db.add(row)
    await db.flush()
    await photos.attach(db, uid, row.id, photo_ids)
    await db.commit()
    return await get_review(db, row.id)


@router.get("/review/v1", response_model=out.PageResponse[out.ReviewResponse])
async def listing(
    theme_id: UUID,
    db: DB,
    keyword: Annotated[list[ReviewKeyword] | None, Query()] = None,
    keyword_match: Literal["any", "all"] = "any",
    people_size: Annotated[int | None, Query(gt=0)] = None,
    sort: Literal["newest", "oldest"] = "newest",
    page: Page = 1,
    page_size: Size = 20,
):
    if not await db.get(Theme, theme_id):
        fail(404, "THEME_NOT_FOUND", "테마를 찾을 수 없습니다.")
    query = views.REVIEW_QUERY.where(Review.theme_id == theme_id)
    if keyword:
        tests = [array_contains(db, Review.review_keyword_list, k) for k in keyword]
        query = query.where(
            Review.keyword_analysis_status == 2, (and_ if keyword_match == "all" else or_)(*tests)
        )
    if people_size:
        query = query.where(
            Review.people_size >= 5 if people_size >= 5 else Review.people_size == people_size
        )
    query = query.order_by(
        Review.created_dt.desc() if sort == "newest" else Review.created_dt,
        Review.id.desc() if sort == "newest" else Review.id,
    )
    return await views.paginate(db, query, page, page_size, views.review)


@router.get("/review/v1/{review_id}", response_model=out.ReviewResponse)
async def detail(review_id: UUID, db: DB):
    return await get_review(db, review_id)


@router.patch("/review/v1/{review_id}", response_model=out.ReviewResponse)
async def patch(review_id: UUID, body: ReviewPatch, db: DB, user: CurrentUser):
    await limit(db, "review:" + str(user.id), 10)
    row = await db.get(Review, review_id)
    if not row:
        fail(404, "REVIEW_NOT_FOUND", "리뷰를 찾을 수 없습니다.")
    if row.user_id != user.id:
        fail(403, "FORBIDDEN", "본인의 리뷰만 수정할 수 있습니다.")
    data = body.model_dump(exclude_unset=True)
    if data.get("played_time") is not None:
        theme = await db.get(Theme, row.theme_id)
        if data["played_time"] > theme.length * 60:
            fail(422, "INVALID_PLAYED_TIME", "플레이 시간이 테마 전체 시간보다 길 수 없습니다.")
    version, old_content, uid = row.updated_dt, row.content, user.id
    await db.rollback()
    if "content" in data and data["content"] != old_content:
        data.update(await keywords.analyze(data["content"]))
    photo_ids = data.pop("photo_ids", None)
    result = await db.execute(
        update(Review)
        .where(Review.id == review_id, Review.user_id == uid, Review.updated_dt == version)
        .values(**data, updated_dt=now())
    )
    if not result.rowcount:
        fail(409, "REVIEW_CHANGED", "리뷰가 변경되거나 삭제되었습니다. 새로고침하세요.")
    if photo_ids is not None:
        await photos.attach(db, uid, review_id, photo_ids)
    await db.commit()
    return await get_review(db, review_id)


@router.delete("/review/v1/{review_id}", status_code=204)
async def delete(review_id: UUID, db: DB, user: CurrentUser):
    row = await db.get(Review, review_id)
    if not row:
        fail(404, "REVIEW_NOT_FOUND", "리뷰를 찾을 수 없습니다.")
    if row.user_id != user.id:
        fail(403, "FORBIDDEN", "본인의 리뷰만 삭제할 수 있습니다.")
    await photos.attach(db, user.id, review_id, [])
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.get("/theme/v1/{theme_id}/review-keywords", response_model=out.KeywordCountsResponse)
async def chips(theme_id: UUID, db: DB, people_size: Annotated[int | None, Query(gt=0)] = None):
    if not await db.get(Theme, theme_id):
        fail(404, "THEME_NOT_FOUND", "테마를 찾을 수 없습니다.")
    items = []
    for code, label in enumerate(LABELS["review_keyword"][1], 1):
        query = select(func.count(Review.id)).where(
            Review.theme_id == theme_id,
            Review.keyword_analysis_status == 2,
            array_contains(db, Review.review_keyword_list, code),
        )
        if people_size:
            query = query.where(
                Review.people_size >= 5 if people_size >= 5 else Review.people_size == people_size
            )
        items.append({"keyword": code, "label": label, "review_count": await db.scalar(query)})
    return {"items": items}
