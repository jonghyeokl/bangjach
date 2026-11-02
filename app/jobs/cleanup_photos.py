"""Remove detached photos older than a day: python -m app.jobs.cleanup_photos."""

import asyncio
from datetime import timedelta

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.database import SessionLocal, engine
from app.domain.models import ReviewPhoto, now
from app.services import photos


async def cleanup(db):
    rows = (
        await db.scalars(
            select(ReviewPhoto)
            .where(
                ReviewPhoto.review_id.is_(None),
                ReviewPhoto.updated_dt < now() - timedelta(days=1),
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    for row in rows:
        await run_in_threadpool(photos.remove, row.object_key)
        await db.delete(row)
    await db.commit()
    return len(rows)


async def main():
    async with SessionLocal() as db:
        count = await cleanup(db)
        print(f"Removed {count} detached photos")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
