from sqlalchemy import exists, or_, select

from app.core.errors import fail
from app.domain.models import Follow, User, UserSetting


def follows(viewer, target):
    return exists(
        select(Follow.id).where(
            Follow.follower_id == viewer, Follow.following_id == target, Follow.status == 2
        )
    )


def visible_condition(viewer, target):
    public = exists(
        select(UserSetting.id).where(
            UserSetting.user_id == target, UserSetting.is_private.is_(False)
        )
    )
    return public if viewer is None else or_(target == viewer, public, follows(viewer, target))


async def check_visibility(db, viewer, target, party=False):
    if not await db.get(User, target):
        fail(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    allowed = await db.scalar(
        select(User.id).where(User.id == target, visible_condition(viewer, User.id))
    )
    if party and viewer != target:
        allowed = allowed and await db.scalar(
            select(UserSetting.id).where(
                UserSetting.user_id == target,
                UserSetting.party_search_enabled.is_(True),
                follows(viewer, target),
            )
        )
    if not allowed:
        fail(403, "PRIVATE", "공개 범위가 허용되지 않습니다.")
