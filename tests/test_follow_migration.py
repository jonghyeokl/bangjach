import os
import sqlite3
import subprocess
import sys
from uuid import uuid4


def test_friend_rows_migrate_without_losing_direction_or_requests(tmp_path):
    path = tmp_path / "migration.db"
    env = {**os.environ, "DATABASE_URL": "sqlite+aiosqlite:///" + str(path)}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "d8e420b1a906"],
        env=env,
        check=True,
        capture_output=True,
    )
    users = sorted([uuid4().hex for _ in range(3)])
    with sqlite3.connect(path) as db:
        for i, uid in enumerate(users):
            db.execute(
                "INSERT INTO user VALUES (?,?,?,?,?,?)",
                (
                    uid,
                    str(i),
                    "test-hash",
                    f"user{i}",
                    "2026-11-01 00:00:00",
                    "2026-11-01 00:00:00",
                ),
            )
            db.execute(
                "INSERT INTO user_setting VALUES (?,?,?,?,?,?)",
                (
                    uuid4().hex,
                    uid,
                    2,
                    1 if i == 0 else 2,
                    "2026-11-01 00:00:00",
                    "2026-11-01 00:00:00",
                ),
            )
        db.execute(
            "INSERT INTO friend VALUES (?,?,?,?,?)",
            (uuid4().hex, users[0], users[1], "2026-11-01 00:00:00", "2026-11-01 00:00:00"),
        )
        db.execute(
            "INSERT INTO friend_request VALUES (?,?,?,?,?)",
            (uuid4().hex, users[2], users[0], "2026-11-01 00:00:00", "2026-11-01 00:00:00"),
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(path) as db:
        assert set(db.execute("SELECT follower_id, following_id, status FROM follow")) == {
            (users[0], users[1], 2),
            (users[1], users[0], 2),
            (users[2], users[0], 1),
        }
        assert db.execute(
            "SELECT is_private, party_search_enabled FROM user_setting WHERE user_id=?", (users[0],)
        ).fetchone() == (1, 0)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
