"""Directional follows, private profiles, subregions and ten review topics."""

from uuid import UUID, uuid4

import sqlalchemy as sa
from alembic import op

revision = "e531a09c7b82"
down_revision = "d8e420b1a906"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    metadata = sa.MetaData()
    old_friend = sa.Table("friend", metadata, autoload_with=db)
    old_request = sa.Table("friend_request", metadata, autoload_with=db)
    friends = list(db.execute(sa.select(old_friend)).mappings())
    requests = list(db.execute(sa.select(old_request)).mappings())
    follow = op.create_table(
        "follow",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("follower_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("following_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("created_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_dt", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("follower_id", "following_id", name="follow_pair"),
        sa.CheckConstraint("follower_id <> following_id", name="follow_self"),
        sa.CheckConstraint("status IN (1, 2)", name="follow_status"),
    )
    op.create_index("ix_follow_follower_id", "follow", ["follower_id"])
    op.create_index("ix_follow_following_id", "follow", ["following_id"])
    seen = set()
    for row in friends:
        for a, b in [
            (row["user_id"], row["other_user_id"]),
            (row["other_user_id"], row["user_id"]),
        ]:
            a, b = UUID(str(a)), UUID(str(b))
            seen.add((a, b))
            db.execute(
                follow.insert().values(
                    id=uuid4(),
                    follower_id=a,
                    following_id=b,
                    status=2,
                    created_dt=row["created_dt"],
                    updated_dt=row["updated_dt"],
                )
            )
    for row in requests:
        a, b = UUID(str(row["requesting_user_id"])), UUID(str(row["requested_user_id"]))
        if (a, b) not in seen:
            db.execute(
                follow.insert().values(
                    id=uuid4(),
                    follower_id=a,
                    following_id=b,
                    status=1,
                    created_dt=row["created_dt"],
                    updated_dt=row["updated_dt"],
                )
            )
    op.drop_table("friend_request")
    op.drop_table("friend")
    with op.batch_alter_table(
        "user_setting",
        recreate="always",
        partial_reordering=[
            (
                "id",
                "user_id",
                "calendar_publicity",
                "party_search_publicity",
                "is_private",
                "party_search_enabled",
                "created_dt",
                "updated_dt",
            )
        ],
    ) as batch:
        batch.add_column(
            sa.Column("is_private", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch.add_column(
            sa.Column(
                "party_search_enabled", sa.Boolean(), server_default=sa.true(), nullable=False
            )
        )
    op.execute("UPDATE user_setting SET party_search_enabled = (party_search_publicity <> 1)")
    with op.batch_alter_table("user_setting") as batch:
        batch.drop_constraint("setting_calendar_publicity", type_="check")
        batch.drop_constraint("setting_party_search_publicity", type_="check")
        batch.drop_column("calendar_publicity")
        batch.drop_column("party_search_publicity")
    if db.dialect.name == "sqlite":
        with op.batch_alter_table(
            "cafe",
            recreate="always",
            partial_reordering=[
                (
                    "id",
                    "name",
                    "website",
                    "phone_number",
                    "region",
                    "subregion",
                    "address",
                    "created_dt",
                    "updated_dt",
                )
            ],
        ) as batch:
            batch.add_column(sa.Column("subregion", sa.Integer(), nullable=True))
            batch.create_check_constraint(
                "cafe_subregion",
                "subregion IS NULL OR (subregion >= region * 100 "
                "AND subregion < (region + 1) * 100)",
            )
    else:
        op.add_column("cafe", sa.Column("subregion", sa.Integer(), nullable=True))
        op.create_check_constraint(
            "cafe_subregion",
            "cafe",
            "subregion IS NULL OR (subregion >= region * 100 AND subregion < (region + 1) * 100)",
        )
    op.create_index("ix_cafe_subregion", "cafe", ["subregion"])
    if db.dialect.name == "postgresql":
        op.drop_constraint("review_review_keyword_list_codes", "review", type_="check")
        op.create_check_constraint(
            "review_review_keyword_list_codes",
            "review",
            "bangjach_valid_codes(review_keyword_list, 10)",
        )
    else:
        for action in ("insert", "update"):
            op.execute(f"DROP TRIGGER review_review_keyword_list_{action}")
            event = "INSERT" if action == "insert" else "UPDATE OF review_keyword_list"
            op.execute(f"""CREATE TRIGGER review_review_keyword_list_{action}
                BEFORE {event} ON review BEGIN
                SELECT CASE WHEN NOT json_valid(NEW.review_keyword_list)
                    THEN RAISE(ABORT, 'Invalid review codes') END;
                SELECT CASE WHEN json_type(NEW.review_keyword_list) <> 'array'
                  OR EXISTS (SELECT 1 FROM json_each(NEW.review_keyword_list)
                    WHERE type <> 'integer' OR value < 1 OR value > 10)
                  OR json_array_length(NEW.review_keyword_list) <>
                    (SELECT count(DISTINCT value) FROM json_each(NEW.review_keyword_list))

                    THEN RAISE(ABORT, 'Invalid review codes') END; END""")


def downgrade():
    raise RuntimeError(
        "Restore a pre-migration backup: directional follows cannot "
        "be losslessly converted to friendships."
    )
