"""add chat_thread_id to users

Revision ID: c1e3f8a92b47
Revises: 4fd462f2a733
Create Date: 2026-02-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1e3f8a92b47'
down_revision: Union[str, None] = '4fd462f2a733'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('chat_thread_id', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'chat_thread_id')
