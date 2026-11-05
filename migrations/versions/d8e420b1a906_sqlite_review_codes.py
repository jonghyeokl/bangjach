"""Keep review enum-array constraints when using SQLite."""

from alembic import op

revision = "d8e420b1a906"
down_revision = "c49af128e307"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "sqlite":
        return
    for column, maximum in (("genre_list", 13), ("review_keyword_list", 7)):
        for action in ("insert", "update"):
            event = "INSERT" if action == "insert" else f"UPDATE OF {column}"
            op.execute(f"""
                CREATE TRIGGER review_{column}_{action}
                BEFORE {event} ON review
                BEGIN
                    SELECT CASE WHEN NOT json_valid(NEW.{column})
                        THEN RAISE(ABORT, 'Invalid review codes') END;
                    SELECT CASE WHEN json_type(NEW.{column}) <> 'array'
                        OR EXISTS (
                            SELECT 1 FROM json_each(NEW.{column})
                            WHERE type <> 'integer' OR value < 1 OR value > {maximum}
                        )
                        OR json_array_length(NEW.{column}) <>
                            (SELECT count(DISTINCT value) FROM json_each(NEW.{column}))
                        THEN RAISE(ABORT, 'Invalid review codes') END;
                END
            """)


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        for column in ("genre_list", "review_keyword_list"):
            for action in ("insert", "update"):
                op.execute(f"DROP TRIGGER review_{column}_{action}")
