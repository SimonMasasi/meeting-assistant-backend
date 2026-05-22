"""add_photo_url_to_users

Revision ID: 0109ac18c412
Revises: dcdfb0af270f
Create Date: 2026-05-22 14:34:32.404661

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0109ac18c412'
down_revision: Union[str, Sequence[str], None] = 'dcdfb0af270f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("photo_url", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "photo_url")
