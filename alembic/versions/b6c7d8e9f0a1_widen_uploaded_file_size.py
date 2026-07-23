"""widen uploaded_files.size to bigint

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-23

uploaded_files.size was a 32-bit integer, which tops out at 2147483647 — one
byte short of 2 GiB. Recording a 2 GB upload therefore failed with "integer out
of range" after the bytes had already been stored. Widened to bigint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6c7d8e9f0a1'
down_revision: Union[str, Sequence[str], None] = 'a5b6c7d8e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('uploaded_files', 'size',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('uploaded_files', 'size',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
