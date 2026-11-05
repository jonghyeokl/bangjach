"""Refresh and verify the repository SQLite statistics, without printing secrets."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.domain.models import Theme, ThemeStatistics, now  # noqa: E402
from app.jobs.statistics import recalculate  # noqa: E402


async def main():
    url = make_url(settings.database_url)
    expected = ROOT / "data/bangjach.db"
    if (
        url.drivername != "sqlite+aiosqlite"
        or Path(url.database or "").resolve() != expected.resolve()
    ):
        raise SystemExit("Refusing: DATABASE_URL must point to this repository's data/bangjach.db")
    if not expected.is_file():
        raise SystemExit("Repository database is missing")
    started = now()
    try:
        async with SessionLocal() as db:
            count = await recalculate(db)
        async with SessionLocal() as db:
            total = await db.scalar(select(func.count(Theme.id)))
            updated = await db.scalar(
                select(func.count(ThemeStatistics.id)).where(ThemeStatistics.updated_dt >= started)
            )
            if count != total or updated != total:
                raise RuntimeError("Statistics verification failed")
        print(f"Updated {count} themes; verification passed")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
