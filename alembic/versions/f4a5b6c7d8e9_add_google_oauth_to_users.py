"""add google oauth to users

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


auth_provider_enum = sa.Enum('LOCAL', 'GOOGLE', name='authproviderenum')


def upgrade() -> None:
    """Upgrade schema."""
    # Google-only accounts have no local password.
    op.alter_column('users', 'password',
               existing_type=sqlmodel.sql.sqltypes.AutoString(),
               nullable=True)

    auth_provider_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('users', sa.Column('auth_provider', auth_provider_enum,
               nullable=False, server_default='LOCAL'))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(),
               nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('google_sub', sqlmodel.sql.sqltypes.AutoString(),
               nullable=True))
    op.create_unique_constraint('uq_users_google_sub', 'users', ['google_sub'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_google_sub', 'users', type_='unique')
    op.drop_column('users', 'google_sub')
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'auth_provider')
    auth_provider_enum.drop(op.get_bind(), checkfirst=True)

    op.alter_column('users', 'password',
               existing_type=sqlmodel.sql.sqltypes.AutoString(),
               nullable=False)
