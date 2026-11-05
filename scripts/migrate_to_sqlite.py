"""Copy every application table from local PostgreSQL into a new SQLite file.

Set SOURCE_DATABASE_URL in the environment; credentials are never printed.
Existing destination files are never overwritten. Stop API/jobs before migrating.
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect, make_url, select, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fingerprint(rows):
    encoded = sorted(json.dumps(dict(row), sort_keys=True, default=str) for row in rows)
    return hashlib.sha256("\n".join(encoded).encode()).hexdigest()


async def migrate(source_url, target_url):
    from app.core.database import Base, create_engine
    from app.domain import models  # noqa: F401

    source = create_async_engine(source_url, isolation_level="REPEATABLE READ")
    target = create_engine(target_url)
    report = {}
    try:
        async with source.begin() as src, target.begin() as dst:
            await src.execute(text("SET TRANSACTION READ ONLY"))
            names = await src.run_sync(lambda conn: inspect(conn).get_table_names())
            if set(names) - {"alembic_version"} != set(Base.metadata.tables):
                raise RuntimeError("Source tables differ from application models; nothing copied")
            for table in Base.metadata.sorted_tables:
                rows = (await src.execute(select(table))).mappings().all()
                for offset in range(0, len(rows), 500):
                    await dst.execute(
                        table.insert(), [dict(r) for r in rows[offset : offset + 500]]
                    )
                copied = (await dst.execute(select(table))).mappings().all()
                before, after = fingerprint(rows), fingerprint(copied)
                if before != after:
                    raise RuntimeError(f"Data verification failed: {table.name}")
                report[table.name] = {"rows": len(rows), "sha256": before}
            if (await dst.execute(text("PRAGMA integrity_check"))).scalars().all() != ["ok"]:
                raise RuntimeError("SQLite integrity check failed")
            if (await dst.execute(text("PRAGMA foreign_key_check"))).all():
                raise RuntimeError("SQLite foreign key check failed")
    finally:
        await source.dispose()
        await target.dispose()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/bangjach.db")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = make_url(os.environ["SOURCE_DATABASE_URL"])
    if source.drivername != "postgresql+asyncpg" or source.host not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Source must be a local PostgreSQL database")
    destination = args.output.resolve()
    if destination.exists():
        raise SystemExit("Destination exists; no data changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = "sqlite+aiosqlite:///" + str(destination)
    # Configure imported application modules and Alembic for the destination.
    os.environ["DATABASE_URL"] = target
    os.environ["ENVIRONMENT"] = "development"
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            check=True,
        )
        report = asyncio.run(migrate(source, target))
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    for table, result in report.items():
        print(f"{table}: {result['rows']} rows verified")
    print("All tables copied and verified; source unchanged.")


if __name__ == "__main__":
    main()
