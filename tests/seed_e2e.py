"""Disposable local database only. Fixture for the app's browser tests."""

import asyncio
from datetime import date
from uuid import UUID

from sqlalchemy import delete

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.domain.models import Cafe, Review, Theme, User, UserSetting
from app.jobs.statistics import recalculate


async def main():
    if engine.url.host not in {"localhost", "127.0.0.1"} or engine.url.username != "bangjach_test":
        raise RuntimeError("Fixture requires a disposable local bangjach_test database")
    async with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            await db.execute(delete(table))
        place = Cafe(
            name="기억의 문 · 테스트 카페",
            phone_number="0200000000",
            region=1,
            address="서울 (테스트 데이터)",
            website="https://example.com",
        )
        db.add(place)
        await db.flush()
        theme = Theme(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            cafe_id=place.id,
            name="사라진 편지",
            description=(
                "오래된 서재에 남겨진 편지 한 장. 잃어버린 이야기를 찾아 떠나는 60분의 여정. "
                "브라우저 검증용 가상 테마입니다."
            ),
            length=60,
        )
        db.add(theme)
        await db.flush()
        for i in range(3):
            user = User(
                phone_number=f"0107000000{i}",
                name=f"테스트친구{i}",
                password_hash=await hash_password("test-password"),
            )
            db.add(user)
            await db.flush()
            db.add(UserSetting(user_id=user.id))
            db.add(
                Review(
                    user_id=user.id,
                    theme_id=theme.id,
                    rating=4 + i * 0.5,
                    date=date(2026, 11, 1),
                    content="이야기와 공간이 인상 깊었어요.",
                    genre_list=[2, 4],
                    review_keyword_list=[1, 4],
                    keyword_analysis_status=2,
                    difficulty=3,
                    horrorness=1,
                    physicality=2,
                )
            )
        await db.commit()
    async with SessionLocal() as db:
        await recalculate(db)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
