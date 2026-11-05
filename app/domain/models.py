from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import UTCDateTime


def now():
    return datetime.now(timezone.utc)


def int_array():
    return JSON().with_variant(ARRAY(Integer), "postgresql")


class Row:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4, sort_order=-100)
    created_dt: Mapped[datetime] = mapped_column(UTCDateTime(), default=now, sort_order=100)
    updated_dt: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=now, onupdate=now, sort_order=101
    )


class User(Row, Base):
    __tablename__ = "user"
    phone_number: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(30), unique=True)


class Cafe(Row, Base):
    __tablename__ = "cafe"
    name: Mapped[str] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(2000))
    phone_number: Mapped[str] = mapped_column(String(30))
    region: Mapped[int] = mapped_column(Integer)
    subregion: Mapped[int | None] = mapped_column(Integer, index=True)
    address: Mapped[str] = mapped_column(String(300))
    __table_args__ = (
        CheckConstraint("region BETWEEN 1 AND 8", name="cafe_region"),
        CheckConstraint(
            "subregion IS NULL OR (subregion >= region * 100 AND subregion < (region + 1) * 100)",
            name="cafe_subregion",
        ),
    )


class Theme(Row, Base):
    __tablename__ = "theme"
    name: Mapped[str] = mapped_column(String(100))
    cafe_id: Mapped[UUID] = mapped_column(ForeignKey("cafe.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(String(10000))
    length: Mapped[int] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(String(2000))
    website: Mapped[str | None] = mapped_column(String(2000))
    __table_args__ = (CheckConstraint("length > 0", name="theme_length"),)


class Review(Row, Base):
    __tablename__ = "review"
    theme_id: Mapped[UUID] = mapped_column(ForeignKey("theme.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"), index=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1))
    date: Mapped[date]
    is_success: Mapped[bool | None]
    people_size: Mapped[int | None]
    hint_count: Mapped[int | None]
    played_time: Mapped[int | None]
    content: Mapped[str | None] = mapped_column(String(5000))
    genre_list: Mapped[list[int]] = mapped_column(int_array(), default=list)
    review_keyword_list: Mapped[list[int]] = mapped_column(int_array(), default=list)
    keyword_analysis_status: Mapped[int] = mapped_column(default=1)
    keyword_analyzed_dt: Mapped[datetime | None] = mapped_column(UTCDateTime())
    keyword_model_version: Mapped[str | None] = mapped_column(String(200))
    difficulty: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    horrorness: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    physicality: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    photos: Mapped[list["ReviewPhoto"]] = relationship(
        order_by="ReviewPhoto.position", passive_deletes=True
    )
    __table_args__ = (
        UniqueConstraint("user_id", "theme_id", name="review_user_theme"),
        *[
            CheckConstraint(
                f"{field} BETWEEN 1 AND 5 AND {field} * 2 = CAST({field} * 2 AS INTEGER)",
                name=f"review_{field}",
            )
            for field in ("rating", "difficulty", "horrorness", "physicality")
        ],
        CheckConstraint("people_size > 0", name="review_people"),
        CheckConstraint("hint_count >= 0", name="review_hints"),
        CheckConstraint("played_time >= 0", name="review_time"),
        CheckConstraint("keyword_analysis_status BETWEEN 1 AND 3", name="review_analysis"),
        Index("review_theme_created", "theme_id", "created_dt", "id"),
        Index("review_user_created", "user_id", "created_dt", "id"),
        Index("review_created", "created_dt", "id"),
        Index("review_calendar", "user_id", "date", "id"),
        Index("review_keywords_gin", "review_keyword_list", postgresql_using="gin").ddl_if(
            dialect="postgresql"
        ),
        Index("review_genres_gin", "genre_list", postgresql_using="gin").ddl_if(
            dialect="postgresql"
        ),
    )


class ReviewLike(Row, Base):
    __tablename__ = "review_like"
    review_id: Mapped[UUID] = mapped_column(ForeignKey("review.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    __table_args__ = (UniqueConstraint("review_id", "user_id", name="review_like_pair"),)


class ReviewPhoto(Row, Base):
    __tablename__ = "review_photo"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), index=True)
    review_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("review.id", ondelete="SET NULL"), index=True
    )
    object_key: Mapped[str] = mapped_column(String(200), unique=True)
    position: Mapped[int] = mapped_column(default=0)


class Follow(Row, Base):
    __tablename__ = "follow"
    follower_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), index=True)
    following_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), index=True)
    status: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="follow_pair"),
        CheckConstraint("follower_id <> following_id", name="follow_self"),
        CheckConstraint("status IN (1, 2)", name="follow_status"),
    )


class UserSetting(Row, Base):
    __tablename__ = "user_setting"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), unique=True)
    is_private: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    party_search_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ThemeStatistics(Row, Base):
    __tablename__ = "theme_statistics"
    theme_id: Mapped[UUID] = mapped_column(ForeignKey("theme.id"), unique=True)
    review_count: Mapped[int] = mapped_column(default=0)
    rating_count: Mapped[int] = mapped_column(default=0)
    difficulty_count: Mapped[int] = mapped_column(default=0)
    horrorness_count: Mapped[int] = mapped_column(default=0)
    physicality_count: Mapped[int] = mapped_column(default=0)
    genre_voter_count: Mapped[int] = mapped_column(default=0)
    avg_rating: Mapped[float | None] = mapped_column(Float)
    normalized_rating: Mapped[float | None] = mapped_column(Float)
    avg_difficulty: Mapped[float | None] = mapped_column(Float)
    avg_horrorness: Mapped[float | None] = mapped_column(Float)
    avg_physicality: Mapped[float | None] = mapped_column(Float)
    most_genre_list: Mapped[list[int] | None] = mapped_column(int_array())
    genre_vote_counts: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    statistics_policy_version: Mapped[str] = mapped_column(String(100))


class AuthSession(Row, Base):
    __tablename__ = "auth_session"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_dt: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_dt: Mapped[datetime | None] = mapped_column(UTCDateTime())


class RateLimit(Base):
    """Shared fixed-window quotas across Cloud Run instances; contains only hashed keys."""

    __tablename__ = "rate_limit"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(default=1)
