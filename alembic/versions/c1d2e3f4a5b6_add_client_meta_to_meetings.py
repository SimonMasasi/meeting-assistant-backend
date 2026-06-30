"""add client_meta to meetings

Revision ID: c1d2e3f4a5b6
Revises: 8bfff273a83d
Create Date: 2026-06-30

Adds a nullable string column on `meetings` that the desktop client uses to
round-trip its presentation-only fields (status, source, tags, host, date, time,
views, attendees, durationLabel, language, createdAt) in cloud mode. The backend
treats it as opaque storage; title/description/created_at stay first-class.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = '8bfff273a83d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'meetings',
        sa.Column('client_meta', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('meetings', 'client_meta')
