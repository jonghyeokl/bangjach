from sqlalchemy import and_, exists, or_, select

from app.core.errors import fail
from app.domain.models import Friend, User, UserSetting


def friend_condition(a, b):
    return or_(
        and_(Friend.user_id == a, Friend.other_user_id == b),
        and_(Friend.user_id == b, Friend.other_user_id == a),
    )


def visible_condition(viewer, field):
    return or_(
        UserSetting.user_id == viewer,
        field == 3,
        and_(
            field == 2,
            exists(select(Friend.id).where(friend_condition(viewer, UserSetting.user_id))),
        ),
    )


async def check_visibility(db, viewer, target, setting):
    if not await db.get(User, target):
        fail(404, "USER_NOT_FOUND", "사용자를 찾을 수 없습니다.")
    allowed = await db.scalar(
        select(UserSetting.id).where(
            UserSetting.user_id == target, visible_condition(viewer, getattr(UserSetting, setting))
        )
    )
    if not allowed:
        fail(403, "PRIVATE", "공개 범위가 허용되지 않습니다.")
