"""Group existing review parties of five or more into the 5+ bucket."""

from alembic import op

revision = "c49af128e307"
down_revision = "b7c81d29e104"
branch_labels = None
depends_on = None


def upgrade():
    op.execute('UPDATE "review" SET people_size = 5 WHERE people_size > 5')


def downgrade():
    # Original sizes cannot be reconstructed; 5 is valid in the previous schema.
    pass
