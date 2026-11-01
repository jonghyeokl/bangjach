from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import aliased

from app.api.users import Page, Size
from app.core.errors import fail
from app.core.security import DB, CurrentUser, lock_pair
from app.domain import responses as out
from app.domain.models import Friend, FriendRequest, User
from app.domain.schemas import FriendCreate
from app.services import views
from app.services.limits import limit
from app.services.privacy import friend_condition

router = APIRouter(tags=["friends"])


def request_view(row, sender, receiver):
    return {
        "id": row.id,
        "requesting_user": views.public_user(sender),
        "requested_user": views.public_user(receiver),
        "created_dt": row.created_dt,
    }


def request_query():
    sender, receiver = aliased(User), aliased(User)
    return (
        select(FriendRequest, sender, receiver)
        .join(sender, sender.id == FriendRequest.requesting_user_id)
        .join(receiver, receiver.id == FriendRequest.requested_user_id)
    )


@router.get("/friend/v1", response_model=out.PageResponse[out.FriendResponse])
async def listing(db: DB, user: CurrentUser, page: Page = 1, page_size: Size = 20):
    query = (
        select(Friend, User)
        .join(
            User,
            or_(
                and_(Friend.user_id == user.id, User.id == Friend.other_user_id),
                and_(Friend.other_user_id == user.id, User.id == Friend.user_id),
            ),
        )
        .order_by(Friend.created_dt.desc(), Friend.id.desc())
    )
    return await views.paginate(
        db,
        query,
        page,
        page_size,
        lambda f, u: {"id": f.id, "friend": views.public_user(u), "created_dt": f.created_dt},
    )


@router.delete("/friend/v1/{friend_id}", status_code=204)
async def remove(friend_id: UUID, db: DB, user: CurrentUser):
    row = await db.get(Friend, friend_id)
    if not row:
        fail(404, "FRIEND_NOT_FOUND", "친구 관계를 찾을 수 없습니다.")
    if user.id not in (row.user_id, row.other_user_id):
        fail(403, "FORBIDDEN", "본인의 친구 관계만 해제할 수 있습니다.")
    await lock_pair(db, row.user_id, row.other_user_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.post("/friend-request/v1", status_code=201, response_model=out.FriendRequestResponse)
async def create(body: FriendCreate, db: DB, user: CurrentUser):
    await limit(db, "friend:" + str(user.id), 20)
    target = await db.scalar(select(User).where(User.name == body.requested_user_name))
    if not target:
        fail(404, "USER_NOT_FOUND", "닉네임을 확인하세요.")
    if target.id == user.id:
        fail(422, "SELF_REQUEST", "본인에게 요청할 수 없습니다.")
    await lock_pair(db, user.id, target.id)
    if await db.scalar(select(Friend.id).where(friend_condition(user.id, target.id))):
        fail(409, "ALREADY_FRIENDS", "이미 친구입니다.")
    pending = or_(
        and_(
            FriendRequest.requesting_user_id == user.id,
            FriendRequest.requested_user_id == target.id,
        ),
        and_(
            FriendRequest.requesting_user_id == target.id,
            FriendRequest.requested_user_id == user.id,
        ),
    )
    if await db.scalar(select(FriendRequest.id).where(pending)):
        fail(409, "REQUEST_EXISTS", "대기 중인 요청이 있습니다. 받은 요청도 확인하세요.")
    row = FriendRequest(requesting_user_id=user.id, requested_user_id=target.id)
    db.add(row)
    await db.commit()
    return request_view(row, user, target)


@router.get("/friend-request/v1", response_model=out.PageResponse[out.FriendRequestResponse])
async def requests(
    db: DB,
    user: CurrentUser,
    direction: Literal["received", "sent"] = "received",
    page: Page = 1,
    page_size: Size = 20,
):
    column = (
        FriendRequest.requested_user_id
        if direction == "received"
        else FriendRequest.requesting_user_id
    )
    query = (
        request_query()
        .where(column == user.id)
        .order_by(FriendRequest.created_dt.desc(), FriendRequest.id.desc())
    )
    return await views.paginate(db, query, page, page_size, request_view)


async def pending(db, request_id, user_id, receiver=True):
    row = await db.get(FriendRequest, request_id)
    if not row:
        fail(404, "REQUEST_NOT_FOUND", "이미 처리되었거나 없는 요청입니다.")
    owner = row.requested_user_id if receiver else row.requesting_user_id
    if owner != user_id:
        fail(403, "FORBIDDEN", "이 요청을 처리할 수 없습니다.")
    await lock_pair(db, row.requesting_user_id, row.requested_user_id)
    row = await db.scalar(
        select(FriendRequest)
        .where(FriendRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        fail(404, "REQUEST_NOT_FOUND", "이미 처리된 요청입니다.")
    return row


@router.post("/friend-request/v1/{request_id}/accept", response_model=out.FriendResponse)
async def accept(request_id: UUID, db: DB, user: CurrentUser):
    row = await pending(db, request_id, user.id)
    target = await db.get(User, row.requesting_user_id)
    first, second = sorted([row.requesting_user_id, row.requested_user_id])
    friend = Friend(user_id=first, other_user_id=second)
    db.add(friend)
    await db.delete(row)
    await db.commit()
    return {"id": friend.id, "friend": views.public_user(target), "created_dt": friend.created_dt}


@router.post("/friend-request/v1/{request_id}/reject", status_code=204)
async def reject(request_id: UUID, db: DB, user: CurrentUser):
    await db.delete(await pending(db, request_id, user.id))
    await db.commit()
    return Response(status_code=204)


@router.delete("/friend-request/v1/{request_id}", status_code=204)
async def cancel(request_id: UUID, db: DB, user: CurrentUser):
    await db.delete(await pending(db, request_id, user.id, False))
    await db.commit()
    return Response(status_code=204)
