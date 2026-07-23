"""add tus_uploads

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-23

Backing table for resumable (tus) uploads, which let large meeting audio (up to
2 GB) be uploaded in chunks and resumed after a dropped connection. A row tracks
the received offset and the scratch file holding the bytes; on completion it
points at the created uploaded_files row.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tus_uploads',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('upload_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('filename', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('total_size', sa.BigInteger(), nullable=False),
        sa.Column('offset', sa.BigInteger(), nullable=False),
        sa.Column('temp_path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('owner_id', sa.BigInteger(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('uploaded_file_id', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['uploaded_file_id'], ['uploaded_files.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('upload_key', name='uq_tus_uploads_upload_key'),
    )
    op.create_index('ix_tus_uploads_upload_key', 'tus_uploads', ['upload_key'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tus_uploads_upload_key', table_name='tus_uploads')
    op.drop_table('tus_uploads')
