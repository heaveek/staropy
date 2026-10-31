"""Add interpretation_templates.position_code (per-card advice keys).

Revision ID: 7f3a1c9d2b45
Revises: d82e561ce0de
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f3a1c9d2b45"
down_revision: Union[str, None] = "d82e561ce0de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interpretation_templates",
        sa.Column("position_code", sa.String(length=96), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interpretation_templates", "position_code")
