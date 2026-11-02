"""Review photo storage references.

Revision ID: b7c81d29e104
Revises: acda55151322
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c81d29e104"
down_revision = "acda55151322"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_photo",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=True),
        sa.Column("object_key", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_dt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_dt", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["review.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_review_photo_user_id", "review_photo", ["user_id"])
    op.create_index("ix_review_photo_review_id", "review_photo", ["review_id"])


def downgrade():
    op.drop_table("review_photo")
