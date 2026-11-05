"""Review likes and recent feed lookup."""

import sqlalchemy as sa
from alembic import op

revision = "a62b18e940fd"
down_revision = "e531a09c7b82"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_like",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "review_id", sa.Uuid(), sa.ForeignKey("review.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_dt", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("review_id", "user_id", name="review_like_pair"),
    )
    op.create_index("ix_review_like_user_id", "review_like", ["user_id"])
    op.create_index("review_created", "review", ["created_dt", "id"])


def downgrade():
    op.drop_index("review_created", table_name="review")
    op.drop_index("ix_review_like_user_id", table_name="review_like")
    op.drop_table("review_like")
