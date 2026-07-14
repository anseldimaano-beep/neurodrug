"""add audit columns

Revision ID: 0002
Revises: 001
Create Date: 2026-06-08
"""
from alembic import op

revision = '0002'
down_revision = '001'
branch_labels = None
depends_on = None

TABLES = [
    'etl_jobs', 'genes', 'drugs', 'interactions', 'diseases',
    'users', 'roles', 'predictions', 'model_versions',
    'training_runs', 'data_sources', 'proteins',
]


def upgrade():
    for table in TABLES:
        op.execute(f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ DEFAULT NOW(),
            ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ DEFAULT NOW(),
            ADD COLUMN IF NOT EXISTS version     INTEGER     DEFAULT 1,
            ADD COLUMN IF NOT EXISTS is_deleted  BOOLEAN     DEFAULT FALSE
        """)


def downgrade():
    pass
