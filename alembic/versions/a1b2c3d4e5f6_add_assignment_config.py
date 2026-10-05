"""add assignment_config table

Revision ID: a1b2c3d4e5f6
Revises: d72bb3507cda
Create Date: 2026-10-04 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d72bb3507cda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assignment_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rider_response_timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("max_search_radius_km", sa.Float(), nullable=False, server_default="10"),
        sa.Column("initial_search_radius_km", sa.Float(), nullable=False, server_default="3"),
        sa.Column("max_assignment_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="0", nullable=False),
        sa.Column("flag", sa.String(length=10), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("assignment_config")
