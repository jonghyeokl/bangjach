"""Daily statistics refresh and cleanup: python -m app.jobs.maintenance."""

import asyncio

from app.core.database import SessionLocal, engine
from app.jobs.cleanup_photos import cleanup
from app.jobs.statistics import recalculate


async def main():
    try:
        async with SessionLocal() as db:
            count = await recalculate(db)
            print(f"Updated statistics for {count} themes")
        async with SessionLocal() as db:
            count = await cleanup(db)
            print(f"Removed {count} detached photos")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
