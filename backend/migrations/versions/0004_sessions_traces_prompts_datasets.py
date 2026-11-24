"""Trace linking and prompt versions on LLM calls; prompt management; datasets and experiments.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('llm_calls') as batch:
        batch.add_column(sa.Column('run_id', sa.String(64), nullable=True))
        batch.add_column(sa.Column('run_step', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('prompt_name', sa.String(120), nullable=False, server_default=''))
        batch.add_column(sa.Column('prompt_version', sa.Integer(), nullable=True))
        batch.create_index('ix_llm_calls_run_id', ['run_id'])
        batch.create_index('ix_llm_ws_session', ['workspace_id', 'session_id'])

    op.create_table(
        'prompts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('template', sa.Text(), nullable=False, server_default=''),
        sa.Column('model', sa.String(120), nullable=False, server_default=''),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('labels', sa.JSON(), nullable=False),
        sa.Column('commit_message', sa.String(500), nullable=False, server_default=''),
        sa.Column('created_by', sa.String(200), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('workspace_id', 'name', 'version'),
    )
    op.create_table(
        'datasets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('workspace_id', 'name'),
    )
    op.create_table(
        'dataset_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('system_prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('input', sa.Text(), nullable=False),
        sa.Column('expected', sa.Text(), nullable=False, server_default=''),
        sa.Column('source_call_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'experiments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('model', sa.String(120), nullable=False),
        sa.Column('credential_id', sa.Integer(), nullable=True),
        sa.Column('prompt_name', sa.String(120), nullable=False, server_default=''),
        sa.Column('prompt_version', sa.Integer(), nullable=True),
        sa.Column('contract_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'experiment_results',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('experiment_id', sa.Integer(), sa.ForeignKey('experiments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('call_id', sa.String(36), nullable=True),
        sa.Column('status', sa.String(10), nullable=False, server_default='ok'),
        sa.Column('output', sa.Text(), nullable=False, server_default=''),
        sa.Column('passed', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('violations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('similarity', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Float(), nullable=False, server_default='0'),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    for t in ('experiment_results', 'experiments', 'dataset_items', 'datasets', 'prompts'):
        op.drop_table(t)
    with op.batch_alter_table('llm_calls') as batch:
        batch.drop_index('ix_llm_ws_session')
        batch.drop_index('ix_llm_calls_run_id')
        for c in ('prompt_version', 'prompt_name', 'run_step', 'run_id'):
            batch.drop_column(c)
