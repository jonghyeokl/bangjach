import calendar
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import case, func, select, update

from app.core.errors import fail
from app.core.security import (
    DB,
    CurrentUser,
    Identity,
    hash_password,
    token_hash,
    tokens,
    utc,
    verify_password,
)
from app.domain import responses as out
from app.domain.models import AuthSession, Follow, Review, User, UserSetting, now
from app.domain.schemas import Login, Refresh, SettingsPatch, Signup, nickname
from app.services import views
from app.services.limits import limit
from app.services.privacy import check_visibility, follows

router = APIRouter(prefix="/user/v1", tags=["users"])
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]


@router.post("/sign-up", status_code=201, response_model=out.UserResponse)
async def signup(body: Signup, db: DB, request: Request):
    await limit(db, "signup:" + (request.client.host if request.client else "unknown"), 10)
    user = User(
        phone_number=body.phone_number,
        name=body.name,
        password_hash=await hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    db.add(UserSetting(user_id=user.id))
    await db.commit()
    return views.own_user(user)


@router.post("/log-in", response_model=out.AuthResponse)
async def login(body: Login, db: DB, request: Request):
    await limit(db, "login-phone:" + body.phone_number, 10)
    await limit(db, "login-ip:" + (request.client.host if request.client else "unknown"), 60)
    user = await db.scalar(select(User).where(User.phone_number == body.phone_number))
    if not user:
        # Comparable password work for unknown accounts.
        await hash_password(body.password)
        fail(401, "BAD_CREDENTIALS", "전화번호 또는 비밀번호를 확인하세요.")
    if not await verify_password(user.password_hash, body.password):
        fail(401, "BAD_CREDENTIALS", "전화번호 또는 비밀번호를 확인하세요.")
    return await tokens(db, user)


@router.post("/refresh", response_model=out.AuthResponse)
async def refresh(body: Refresh, db: DB):
    session = await db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == token_hash(body.refresh_token))
        .with_for_update()
    )
    if not session or session.revoked_dt or utc(session.expires_dt) <= now():
        fail(401, "UNAUTHORIZED", "다시 로그인하세요.")
    return await tokens(db, await db.get(User, session.user_id), session)


@router.post("/log-out", status_code=204)
async def logout(who: Identity, db: DB):
    if not who:
        fail(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    # Lock in the same way as token rotation so logout cannot resurrect a session.
    session = await db.scalar(
        select(AuthSession).where(AuthSession.id == who[1].id).with_for_update()
    )
    session.revoked_dt = now()
    await db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=out.UserResponse)
async def me(user: CurrentUser):
    return views.own_user(user)


@router.get("/search", response_model=out.PageResponse[out.PublicUserResponse])
async def search(
    db: DB,
    user: CurrentUser,
    q: Annotated[str, Query(min_length=1, max_length=30)],
    purpose: Literal["follow", "party"] = "follow",
    page: Page = 1,
    page_size: Size = 20,
):
    try:
        q = nickname(q)
    except ValueError:
        fail(422, "INVALID_NICKNAME", "검색할 닉네임을 입력하세요.")
    query = select(User).where(User.name.contains(q, autoescape=True), User.id != user.id)
    if purpose == "party":
        query = query.join(UserSetting).where(
            follows(user.id, User.id),
            UserSetting.party_search_enabled.is_(True),
        )
    query = query.order_by(case((User.name == q, 0), else_=1), User.name, User.id)
    return await views.paginate(db, query, page, page_size, views.public_user)


@router.get("/me/settings", response_model=out.UserSettingResponse)
async def get_settings(db: DB, user: CurrentUser):
    row = await db.scalar(select(UserSetting).where(UserSetting.user_id == user.id))
    return views.fields(row, "is_private party_search_enabled updated_dt")


@router.patch("/me/settings", response_model=out.UserSettingResponse)
async def patch_settings(body: SettingsPatch, db: DB, user: CurrentUser):
    await db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    row = await db.scalar(
        select(UserSetting).where(UserSetting.user_id == user.id).with_for_update()
    )
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    if body.is_private is False:
        await db.execute(
            update(Follow)
            .where(Follow.following_id == user.id, Follow.status == 1)
            .values(status=2)
        )
    await db.commit()
    return views.fields(row, "is_private party_search_enabled updated_dt")


@router.get("/me/reviews", response_model=out.PageResponse[out.ReviewResponse])
async def my_reviews(
    db: DB,
    user: CurrentUser,
    page: Page = 1,
    page_size: Size = 20,
    theme_id: UUID | None = None,
):
    query = views.review_query(user.id).where(Review.user_id == user.id)
    if theme_id is not None:
        query = query.where(Review.theme_id == theme_id)
    return await views.paginate(
        db,
        query.order_by(Review.created_dt.desc(), Review.id.desc()),
        page,
        page_size,
        views.review,
    )


@router.get("/{user_id}/calendar", response_model=out.CalendarResponse)
async def get_calendar(
    user_id: UUID, db: DB, user: CurrentUser, month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]
):
    try:
        first = date.fromisoformat(month + "-01")
        last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
    except ValueError:
        fail(422, "INVALID_MONTH", "월은 YYYY-MM 형식입니다.")
    await check_visibility(db, user.id, user_id)
    rows = (
        await db.execute(
            views.REVIEW_QUERY.where(
                Review.user_id == user_id, Review.date >= first, Review.date <= last
            ).order_by(Review.date, Review.id)
        )
    ).all()
    target = await db.get(User, user_id)
    return {
        "user": views.public_user(target),
        "month": month,
        "items": [
            {
                "review_id": r.id,
                "theme_id": t.id,
                "theme_name": t.name,
                "cafe_name": c.name,
                "image_url": t.image_url,
                "date": r.date,
                "rating": float(r.rating),
                "is_success": r.is_success,
            }
            for r, _, t, c in rows
        ],
    }


@router.get("/{user_id}/profile", response_model=out.ProfileResponse)
async def profile(user_id: UUID, db: DB, viewer: CurrentUser):
    target = await db.get(User, user_id)
    if not target:
        fail(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    private = await db.scalar(select(UserSetting.is_private).where(UserSetting.user_id == user_id))
    row = await db.scalar(
        select(Follow).where(Follow.follower_id == viewer.id, Follow.following_id == user_id)
    )
    can_view = viewer.id == user_id or private is False or (row is not None and row.status == 2)
    counts = {"review_count": None, "follower_count": None, "following_count": None}
    if can_view:
        counts = {
            "review_count": await db.scalar(
                select(func.count(Review.id)).where(Review.user_id == user_id)
            ),
            "follower_count": await db.scalar(
                select(func.count(Follow.id)).where(
                    Follow.following_id == user_id, Follow.status == 2
                )
            ),
            "following_count": await db.scalar(
                select(func.count(Follow.id)).where(
                    Follow.follower_id == user_id, Follow.status == 2
                )
            ),
        }
    return {
        **views.public_user(target),
        **counts,
        "is_private": private is not False,
        "can_view": can_view,
        "is_self": viewer.id == user_id,
        "relationship": "following" if row and row.status == 2 else "pending" if row else "none",
        "follow_id": row.id if row else None,
    }


@router.get("/{user_id}/reviews", response_model=out.PageResponse[out.ReviewResponse])
async def user_reviews(
    user_id: UUID, db: DB, user: CurrentUser, page: Page = 1, page_size: Size = 20
):
    await check_visibility(db, user.id, user_id)
    return await views.paginate(
        db,
        views.review_query(user.id)
        .where(Review.user_id == user_id)
        .order_by(Review.created_dt.desc(), Review.id.desc()),
        page,
        page_size,
        views.review,
    )
