import pytest
from sqlalchemy import inspect

from app.core.database import Base


@pytest.mark.asyncio
async def test_id_and_timestamps_have_consistent_physical_order(factory):
    async with factory() as session:
        connection = await session.connection()

        def check(sync_connection):
            inspector = inspect(sync_connection)
            for name, table in Base.metadata.tables.items():
                columns = [column["name"] for column in inspector.get_columns(name)]
                if name == "rate_limit":
                    assert columns == ["key", "window", "count"]
                    continue
                assert columns[0] == "id", name
                if connection.dialect.name == "postgresql" and name == "cafe":
                    # PostgreSQL appends added columns; avoid rebuilding a referenced table.
                    assert set(table.c.keys()) == set(columns)
                    continue
                assert columns[-2:] == ["created_dt", "updated_dt"], name
                assert list(table.c.keys()) == columns, name

        await connection.run_sync(check)
