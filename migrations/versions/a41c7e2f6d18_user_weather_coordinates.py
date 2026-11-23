"""Add saved user weather coordinates.

Revision ID: a41c7e2f6d18
Revises: 9f4b7c2d1a63
"""
from alembic import op
import sqlalchemy as sa


revision = "a41c7e2f6d18"
down_revision = "9f4b7c2d1a63"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
