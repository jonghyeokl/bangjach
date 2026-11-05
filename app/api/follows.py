from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.users import Page, Size
from app.core.errors import fail
from app.core.security import DB, CurrentUser, lock_pair
from app.domain import responses as out
from app.domain.models import Follow, User, UserSetting
from app.domain.schemas import FollowCreate
from app.services import views
from app.services.limits import limit
from app.services.privacy import check_visibility

router = APIRouter(prefix="/follow/v1", tags=["follows"])


def view(row, user):
    return {
        "id": row.id,
        "user": views.public_user(user),
        "status": row.status,
        "created_dt": row.created_dt,
    }


@router.post("", response_model=out.FollowResponse)
async def create(body: FollowCreate, db: DB, user: CurrentUser):
    await limit(db, "follow:" + str(user.id), 30)
    target = await db.get(User, body.user_id)
    if not target:
        fail(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    if target.id == user.id:
        fail(422, "SELF_FOLLOW", "본인은 팔로우할 수 없습니다.")
    await lock_pair(db, user.id, target.id)
    row = await db.scalar(
        select(Follow).where(Follow.follower_id == user.id, Follow.following_id == target.id)
    )
    if row is None:
        private = await db.scalar(
            select(UserSetting.is_private).where(UserSetting.user_id == target.id)
        )
        row = Follow(
            follower_id=user.id, following_id=target.id, status=1 if private is not False else 2
        )
        db.add(row)
        await db.commit()
    return view(row, target)


@router.get("", response_model=out.PageResponse[out.FollowResponse])
async def listing(
    db: DB,
    user: CurrentUser,
    user_id: UUID | None = None,
    direction: Literal["followers", "following", "requests"] = "following",
    page: Page = 1,
    page_size: Size = 20,
):
    target = user_id or user.id
    if direction == "requests" and target != user.id:
        fail(403, "FORBIDDEN", "본인의 요청만 확인할 수 있습니다.")
    await check_visibility(db, user.id, target)
    outgoing = direction == "following"
    query = (
        select(Follow, User)
        .join(User, User.id == (Follow.following_id if outgoing else Follow.follower_id))
        .where(
            (Follow.follower_id if outgoing else Follow.following_id) == target,
            Follow.status == (1 if direction == "requests" else 2),
        )
        .order_by(Follow.created_dt.desc(), Follow.id.desc())
    )
    return await views.paginate(db, query, page, page_size, view)


@router.post("/{follow_id}/accept", response_model=out.FollowResponse)
async def accept(follow_id: UUID, db: DB, user: CurrentUser):
    row = await db.get(Follow, follow_id)
    if not row:
        fail(404, "FOLLOW_NOT_FOUND", "요청을 찾을 수 없습니다.")
    if row.following_id != user.id:
        fail(403, "FORBIDDEN", "받은 요청만 승인할 수 있습니다.")
    await lock_pair(db, row.follower_id, row.following_id)
    row = await db.scalar(
        select(Follow)
        .where(Follow.id == follow_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        fail(404, "FOLLOW_NOT_FOUND", "요청을 찾을 수 없습니다.")
    row.status = 2
    target = await db.get(User, row.follower_id)
    await db.commit()
    return view(row, target)


@router.delete("/{follow_id}", status_code=204)
async def remove(follow_id: UUID, db: DB, user: CurrentUser):
    row = await db.get(Follow, follow_id)
    if not row:
        fail(404, "FOLLOW_NOT_FOUND", "팔로우 관계를 찾을 수 없습니다.")
    if user.id not in (row.follower_id, row.following_id):
        fail(403, "FORBIDDEN", "본인의 팔로우 관계만 변경할 수 있습니다.")
    await lock_pair(db, row.follower_id, row.following_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
