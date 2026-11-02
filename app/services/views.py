from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.domain.models import Cafe, Review, Theme, ThemeStatistics, User

COUNTS = [
    "review_count",
    "rating_count",
    "difficulty_count",
    "horrorness_count",
    "physicality_count",
    "genre_voter_count",
]
VALUES = [
    "avg_rating",
    "normalized_rating",
    "avg_difficulty",
    "avg_horrorness",
    "avg_physicality",
    "most_genre_list",
    "statistics_policy_version",
    "updated_dt",
]


def public_user(user):
    return {"id": user.id, "name": user.name}


def own_user(user):
    return {
        **public_user(user),
        "phone_number": user.phone_number,
        "is_admin": str(user.id) in settings.admin_user_ids,
        "created_dt": user.created_dt,
        "updated_dt": user.updated_dt,
    }


def fields(row, names):
    return {name: getattr(row, name) for name in names.split()}


def stats(row):
    if row is None:
        return {**dict.fromkeys(COUNTS, 0), **dict.fromkeys(VALUES), "genre_vote_counts": {}}
    return {key: getattr(row, key) for key in COUNTS + VALUES + ["genre_vote_counts"]}


def cafe(row):
    return fields(row, "id name website phone_number region address")


def theme(row, place, statistics, detail=False):
    data = {
        **fields(row, "id name image_url length created_dt"),
        "cafe": fields(place, "id name region"),
        "statistics": stats(statistics),
    }
    if detail:
        data.update(
            cafe=cafe(place),
            description=row.description,
            website=row.website or place.website,
            updated_dt=row.updated_dt,
        )
    return data


def review(row, user, target, place):
    data = fields(
        row,
        "id theme_id rating date is_success people_size hint_count played_time content "
        "genre_list review_keyword_list keyword_analysis_status keyword_analyzed_dt "
        "difficulty horrorness physicality created_dt updated_dt",
    )
    for field in ("rating", "difficulty", "horrorness", "physicality"):
        data[field] = float(data[field]) if data[field] is not None else None
    return {
        **data,
        "author": public_user(user),
        "theme_name": target.name,
        "theme_image_url": target.image_url,
        "photos": [{"id": p.id, "url": f"/media/v1/review-photos/{p.id}"} for p in row.photos],
        "cafe_name": place.name,
    }


REVIEW_QUERY = (
    select(Review, User, Theme, Cafe)
    .options(selectinload(Review.photos))
    .join(User, Review.user_id == User.id)
    .join(Theme, Review.theme_id == Theme.id)
    .join(Cafe, Theme.cafe_id == Cafe.id)
)
THEME_QUERY = (
    select(Theme, Cafe, ThemeStatistics)
    .join(Cafe)
    .outerjoin(ThemeStatistics, ThemeStatistics.theme_id == Theme.id)
)


async def paginate(db, query, page, page_size, convert):
    total = await db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = (await db.execute(query.offset((page - 1) * page_size).limit(page_size))).all()
    return {
        "items": [convert(*row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
