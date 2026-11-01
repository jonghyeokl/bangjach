import hashlib
import time

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.core.errors import fail
from app.domain.models import RateLimit


async def limit(db, key: str, maximum: int, seconds: int = 60):
    if not settings.rate_limit_enabled:
        return
    # Each call has its own short transaction, never holding the quota while awaiting LLM.
    timestamp = int(time.time())
    bucket = timestamp // seconds * seconds
    hashed = hashlib.sha256(key.encode()).hexdigest()
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    query = insert(RateLimit).values(key=hashed, window=bucket, count=1)
    query = query.on_conflict_do_update(
        index_elements=[RateLimit.key, RateLimit.window], set_={"count": RateLimit.count + 1}
    ).returning(RateLimit.count)
    count = await db.scalar(query)
    await db.execute(delete(RateLimit).where(RateLimit.window < timestamp - 86400))
    await db.commit()
    if count > maximum:
        fail(429, "RATE_LIMITED", "잠시 후 다시 시도하세요.")
