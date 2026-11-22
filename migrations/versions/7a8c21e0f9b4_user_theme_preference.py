"""Persist each user's day or night theme preference.

Revision ID: 7a8c21e0f9b4
Revises: 9f4b7c2d1a63
"""
from alembic import op
import sqlalchemy as sa


revision = "7a8c21e0f9b4"
down_revision = "9f4b7c2d1a63"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("theme", sa.String(length=10), nullable=False, server_default="day"),
    )


def downgrade():
    op.drop_column("user", "theme")
