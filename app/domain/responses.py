from datetime import date, datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel

T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class PublicUserResponse(BaseModel):
    id: UUID
    name: str


class UserResponse(PublicUserResponse):
    phone_number: str
    created_dt: datetime
    updated_dt: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user: UserResponse


class UserSettingResponse(BaseModel):
    calendar_publicity: int
    party_search_publicity: int
    updated_dt: datetime


class CafeResponse(BaseModel):
    id: UUID
    name: str
    website: str | None
    phone_number: str
    region: int
    address: str


class ThemeStatisticsResponse(BaseModel):
    review_count: int
    rating_count: int
    difficulty_count: int
    horrorness_count: int
    physicality_count: int
    genre_voter_count: int
    avg_rating: float | None
    normalized_rating: float | None
    avg_difficulty: float | None
    avg_horrorness: float | None
    avg_physicality: float | None
    most_genre_list: list[int] | None
    genre_vote_counts: dict[str, int]
    statistics_policy_version: str | None
    updated_dt: datetime | None


class CafeSummaryResponse(BaseModel):
    id: UUID
    name: str
    region: int


class ThemeSummaryResponse(BaseModel):
    id: UUID
    name: str
    cafe: CafeSummaryResponse
    image_url: str | None
    length: int
    statistics: ThemeStatisticsResponse
    created_dt: datetime


class ThemeResponse(ThemeSummaryResponse):
    cafe: CafeResponse
    description: str
    website: str | None
    updated_dt: datetime


class PhotoResponse(BaseModel):
    id: UUID
    url: str


class ReviewResponse(BaseModel):
    id: UUID
    theme_id: UUID
    theme_name: str
    theme_image_url: str | None
    photos: list[PhotoResponse]
    cafe_name: str
    author: PublicUserResponse
    rating: float
    date: date
    is_success: bool | None
    people_size: int | None
    hint_count: int | None
    played_time: int | None
    content: str | None
    genre_list: list[int]
    review_keyword_list: list[int]
    keyword_analysis_status: int
    keyword_analyzed_dt: datetime | None
    difficulty: float | None
    horrorness: float | None
    physicality: float | None
    created_dt: datetime
    updated_dt: datetime


class FriendResponse(BaseModel):
    id: UUID
    friend: PublicUserResponse
    created_dt: datetime


class FriendRequestResponse(BaseModel):
    id: UUID
    requesting_user: PublicUserResponse
    requested_user: PublicUserResponse
    created_dt: datetime


class CalendarItem(BaseModel):
    review_id: UUID
    theme_id: UUID
    theme_name: str
    cafe_name: str
    image_url: str | None
    date: date
    rating: float
    is_success: bool | None


class CalendarResponse(BaseModel):
    user: PublicUserResponse
    month: str
    items: list[CalendarItem]


class KeywordCount(BaseModel):
    keyword: int
    label: str
    review_count: int


class KeywordCountsResponse(BaseModel):
    items: list[KeywordCount]


class EnumOption(BaseModel):
    value: int
    label: str
