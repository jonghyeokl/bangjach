"""Run with python -m app.jobs.statistics; one atomic daily snapshot."""

import asyncio
from collections import Counter, defaultdict
from statistics import mean

from sqlalchemy import select, text

from app.core.database import SessionLocal, engine
from app.domain.models import Review, Theme, ThemeStatistics, now

POLICY = "user_bias_v1(lambda=10,min_samples=3)"


async def recalculate(db):
    # Configure isolation before the first read: aggregates must share one snapshot.
    if db.bind.dialect.name == "postgresql":
        await db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        if not await db.scalar(text("SELECT pg_try_advisory_xact_lock(73402611)")):
            return 0
    reviews = (await db.scalars(select(Review))).all()
    by_user, by_theme = defaultdict(list), defaultdict(list)
    for review in reviews:
        by_user[review.user_id].append(float(review.rating))
        by_theme[review.theme_id].append(review)
    global_mean = mean([float(r.rating) for r in reviews]) if reviews else 0
    biases = {
        uid: len(values) / (len(values) + 10) * (mean(values) - global_mean)
        for uid, values in by_user.items()
    }
    existing = {s.theme_id: s for s in (await db.scalars(select(ThemeStatistics))).all()}
    ids = (await db.scalars(select(Theme.id))).all()
    timestamp = now()
    for tid in ids:
        rows = by_theme[tid]
        stat = existing.get(tid)
        if stat is None:
            stat = ThemeStatistics(theme_id=tid)
            db.add(stat)
        stat.review_count = len(rows)
        for field in ("rating", "difficulty", "horrorness", "physicality"):
            values = [float(getattr(r, field)) for r in rows if getattr(r, field) is not None]
            setattr(stat, field + "_count", len(values))
            setattr(stat, "avg_" + field, mean(values) if len(values) >= 3 else None)
        stat.normalized_rating = (
            max(1, min(5, mean([float(r.rating) - biases[r.user_id] for r in rows])))
            if len(rows) >= 3
            else None
        )
        votes = Counter(g for r in rows for g in set(r.genre_list))
        stat.genre_voter_count = sum(bool(r.genre_list) for r in rows)
        stat.genre_vote_counts = {str(k): v for k, v in sorted(votes.items())}
        stat.most_genre_list = (
            sorted(k for k, v in votes.items() if v == max(votes.values()))
            if stat.genre_voter_count >= 3
            else None
        )
        stat.statistics_policy_version = POLICY
        stat.updated_dt = timestamp
    await db.commit()
    return len(ids)


async def main():
    async with SessionLocal() as db:
        count = await recalculate(db)
        print(f"Updated statistics for {count} themes")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
