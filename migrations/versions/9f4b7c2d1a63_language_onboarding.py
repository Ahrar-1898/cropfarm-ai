"""Persist language onboarding completion.

Revision ID: 9f4b7c2d1a63
Revises: 3cd3914451a0
"""
from alembic import op
import sqlalchemy as sa


revision = "9f4b7c2d1a63"
down_revision = "3cd3914451a0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "language_onboarding_done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade():
    op.drop_column("user", "language_onboarding_done")
