from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def create_engine(url, **kwargs):
    """SQLite serializes transactions to preserve read-then-write invariants locally."""
    engine = create_async_engine(url, pool_pre_ping=True, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_config(connection, _):
            connection.isolation_level = None
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")

        @event.listens_for(engine.sync_engine, "begin")
        def sqlite_begin(connection):
            # SQLite ignores FOR UPDATE. Reserve the writer before the first read
            # so refresh rotation, friend requests and photo ownership stay atomic.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


engine = create_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with SessionLocal() as session:
        yield session
