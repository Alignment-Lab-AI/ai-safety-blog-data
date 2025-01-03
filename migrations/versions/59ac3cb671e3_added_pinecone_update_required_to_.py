"""Added pinecone_update_required to articles

Revision ID: 59ac3cb671e3
Revises: 0a0041c28458
Create Date: 2023-08-06 22:11:42.765662

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "59ac3cb671e3"
down_revision = "0a0041c28458"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("pinecone_update_required", sa.Boolean(), nullable=False))


def downgrade() -> None:
    op.drop_column("articles", "pinecone_update_required")
