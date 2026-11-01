import re
import unicodedata
from datetime import date as Date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    PlainSerializer,
    field_validator,
    model_validator,
)

from app.domain.enums import Genre, Publicity, Region


def score(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, Decimal)):
        raise ValueError("점수는 숫자로 입력하세요.")
    d = Decimal(str(v))
    if not d.is_finite() or not 1 <= d <= 5 or d % Decimal("0.5"):
        raise ValueError("점수는 1~5, 0.5 간격입니다.")
    return d


def day(v):
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ValueError("플레이 날짜는 YYYY-MM-DD 형식입니다.")
    return v


def nickname(v: str):
    v = unicodedata.normalize("NFC", v).strip()
    if not 1 <= len(v) <= 30 or any(unicodedata.category(c).startswith("C") for c in v):
        raise ValueError("닉네임은 공백을 제외한 1~30자입니다.")
    return v


def phone(v: str):
    v = re.sub(r"[\s()-]", "", v)
    if not re.fullmatch(r"\+?\d{8,15}", v):
        raise ValueError("올바른 전화번호를 입력하세요.")
    if v.startswith("+82"):
        v = "0" + v[3:]
    return v


Score = Annotated[Decimal, BeforeValidator(score), PlainSerializer(float, return_type=float)]
PlayDate = Annotated[Date, BeforeValidator(day)]
Name = Annotated[str, AfterValidator(nickname)]
Phone = Annotated[str, AfterValidator(phone)]
Url = Annotated[HttpUrl, PlainSerializer(str, return_type=str)]
Positive = Annotated[int, Field(strict=True, gt=0)]
Nonnegative = Annotated[int, Field(strict=True, ge=0)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    phone_number: Phone
    password: str = Field(min_length=1, max_length=128)


class Signup(Login):
    name: Name
    password: str = Field(min_length=8, max_length=128)


class Refresh(Input):
    refresh_token: str = Field(min_length=20, max_length=200)


class Patch(Input):
    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("변경할 값을 입력하세요.")
        for field in self.model_fields_set & set(self.required_values()):
            if getattr(self, field) is None:
                raise ValueError(f"{field}는 null일 수 없습니다.")
        return self

    def required_values(self):
        return []


class SettingsPatch(Patch):
    calendar_publicity: Publicity | None = None
    party_search_publicity: Publicity | None = None

    def required_values(self):
        return ["calendar_publicity", "party_search_publicity"]


class ReviewFields(Input):
    is_success: bool | None = Field(default=None, strict=True)
    people_size: Positive | None = None
    hint_count: Nonnegative | None = None
    played_time: Nonnegative | None = None
    content: str | None = Field(default=None, max_length=5000)
    genre_list: list[Genre] = Field(default_factory=list, max_length=30)
    difficulty: Score | None = None
    horrorness: Score | None = None
    physicality: Score | None = None

    @field_validator("content")
    @classmethod
    def trim(cls, v):
        return v.strip() or None if v is not None else None

    @field_validator("genre_list")
    @classmethod
    def genres(cls, v):
        return sorted(set(v))


class ReviewCreate(ReviewFields):
    theme_id: UUID
    rating: Score
    date: PlayDate


class ReviewPatch(ReviewFields, Patch):
    rating: Score | None = None
    date: PlayDate | None = None

    def required_values(self):
        return ["rating", "date", "genre_list"]


class CafeCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    website: Url | None = None
    phone_number: str = Field(min_length=1, max_length=30)
    region: Region
    address: str = Field(min_length=1, max_length=300)


class ThemeCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    cafe_id: UUID
    description: str = Field(max_length=10000)
    length: Positive
    image_url: Url | None = None
    website: Url | None = None


class FriendCreate(Input):
    requested_user_name: Name
