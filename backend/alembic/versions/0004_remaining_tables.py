"""Create remaining model tables missing from earlier migrations.

Revision ID: 0004_remaining_tables
Revises: 0003_assets_table

Several SQLAlchemy models (api keys, audit events, notifications,
compliance, playbooks, etc.) never had migration DDL. Any endpoint
querying those tables 500s on Postgres with 'relation does not exist'.
Generated from the model metadata; enum columns use VARCHAR(50) per
the 0001 convention.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_remaining_tables"
down_revision: Union[str, None] = "0003_assets_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'compliance_frameworks',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('version', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_compliance_frameworks_id', 'compliance_frameworks', ['id'], unique=False)
    op.create_index('ix_compliance_frameworks_name', 'compliance_frameworks', ['name'], unique=False)
    op.create_index('ix_compliance_frameworks_tenant_id', 'compliance_frameworks', ['tenant_id'], unique=False)
    op.create_table(
        'intelligence_metrics',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('metric_name', sa.String(length=255), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('dimensions', sa.JSON(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_intelligence_metrics_metric_name', 'intelligence_metrics', ['metric_name'], unique=False)
    op.create_index('ix_intelligence_metrics_id', 'intelligence_metrics', ['id'], unique=False)
    op.create_index('ix_intelligence_metrics_tenant_id', 'intelligence_metrics', ['tenant_id'], unique=False)
    op.create_table(
        'notification_history',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('event_type', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_notification_history_tenant_id', 'notification_history', ['tenant_id'], unique=False)
    op.create_index('ix_notification_history_id', 'notification_history', ['id'], unique=False)
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('min_severity', sa.String(length=50), nullable=False),
        sa.Column('quiet_hours_start', sa.Time(), nullable=True),
        sa.Column('quiet_hours_end', sa.Time(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=False),
    )
    op.create_index('ix_notification_preferences_id', 'notification_preferences', ['id'], unique=False)
    op.create_index('ix_notification_preferences_tenant_id', 'notification_preferences', ['tenant_id'], unique=False)
    op.create_table(
        'playbooks',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('definition', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_playbooks_name', 'playbooks', ['name'], unique=False)
    op.create_index('ix_playbooks_tenant_id', 'playbooks', ['tenant_id'], unique=False)
    op.create_index('ix_playbooks_id', 'playbooks', ['id'], unique=False)
    op.create_table(
        'tenant_key_store',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, unique=True),
        sa.Column('encrypted_dek', sa.String(length=2048), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_tenant_key_store_id', 'tenant_key_store', ['id'], unique=False)
    op.create_index('ix_tenant_key_store_tenant_id', 'tenant_key_store', ['tenant_id'], unique=True)
    op.create_table(
        'webhook_endpoints',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('url', sa.String(length=1024), nullable=False),
        sa.Column('secret', sa.String(length=2048), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
    )
    op.create_index('ix_webhook_endpoints_tenant_id', 'webhook_endpoints', ['tenant_id'], unique=False)
    op.create_index('ix_webhook_endpoints_id', 'webhook_endpoints', ['id'], unique=False)
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Uuid(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('key_prefix', sa.String(length=8), nullable=False, unique=True),
        sa.Column('key_hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)
    op.create_index('ix_api_keys_tenant_id', 'api_keys', ['tenant_id'], unique=False)
    op.create_index('ix_api_keys_key_prefix', 'api_keys', ['key_prefix'], unique=True)
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('trace_id', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=255), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('integrity_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_audit_events_action', 'audit_events', ['action'], unique=False)
    op.create_index('ix_audit_events_trace_id', 'audit_events', ['trace_id'], unique=False)
    op.create_index('ix_audit_events_user_id', 'audit_events', ['user_id'], unique=False)
    op.create_index('ix_audit_events_id', 'audit_events', ['id'], unique=False)
    op.create_index('ix_audit_events_tenant_id', 'audit_events', ['tenant_id'], unique=False)
    op.create_table(
        'compliance_controls',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('framework_id', sa.Integer(), sa.ForeignKey('compliance_frameworks.id'), nullable=False),
        sa.Column('control_id', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
    )
    op.create_index('ix_compliance_controls_id', 'compliance_controls', ['id'], unique=False)
    op.create_index('ix_compliance_controls_control_id', 'compliance_controls', ['control_id'], unique=False)
    op.create_index('ix_compliance_controls_framework_id', 'compliance_controls', ['framework_id'], unique=False)
    op.create_table(
        'playbook_executions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('playbook_id', sa.Integer(), sa.ForeignKey('playbooks.id'), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('context_data', sa.JSON(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_playbook_executions_playbook_id', 'playbook_executions', ['playbook_id'], unique=False)
    op.create_index('ix_playbook_executions_tenant_id', 'playbook_executions', ['tenant_id'], unique=False)
    op.create_index('ix_playbook_executions_id', 'playbook_executions', ['id'], unique=False)
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('execution_id', sa.Integer(), sa.ForeignKey('playbook_executions.id'), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('requester_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approver_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_approval_requests_execution_id', 'approval_requests', ['execution_id'], unique=False)
    op.create_index('ix_approval_requests_tenant_id', 'approval_requests', ['tenant_id'], unique=False)
    op.create_index('ix_approval_requests_id', 'approval_requests', ['id'], unique=False)
    op.create_table(
        'compliance_rules',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('control_id', sa.Integer(), sa.ForeignKey('compliance_controls.id'), nullable=False),
        sa.Column('rule_expression', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
    )
    op.create_index('ix_compliance_rules_control_id', 'compliance_rules', ['control_id'], unique=False)
    op.create_index('ix_compliance_rules_id', 'compliance_rules', ['id'], unique=False)
    op.create_table(
        'compliance_violations',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('rule_id', sa.Integer(), sa.ForeignKey('compliance_rules.id'), nullable=False),
        sa.Column('asset_id', sa.String(length=255), nullable=True),
        sa.Column('event_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_compliance_violations_rule_id', 'compliance_violations', ['rule_id'], unique=False)
    op.create_index('ix_compliance_violations_tenant_id', 'compliance_violations', ['tenant_id'], unique=False)
    op.create_index('ix_compliance_violations_id', 'compliance_violations', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_compliance_violations_rule_id', table_name='compliance_violations')
    op.drop_index('ix_compliance_violations_tenant_id', table_name='compliance_violations')
    op.drop_index('ix_compliance_violations_id', table_name='compliance_violations')
    op.drop_table('compliance_violations')
    op.drop_index('ix_compliance_rules_control_id', table_name='compliance_rules')
    op.drop_index('ix_compliance_rules_id', table_name='compliance_rules')
    op.drop_table('compliance_rules')
    op.drop_index('ix_approval_requests_execution_id', table_name='approval_requests')
    op.drop_index('ix_approval_requests_tenant_id', table_name='approval_requests')
    op.drop_index('ix_approval_requests_id', table_name='approval_requests')
    op.drop_table('approval_requests')
    op.drop_index('ix_playbook_executions_playbook_id', table_name='playbook_executions')
    op.drop_index('ix_playbook_executions_tenant_id', table_name='playbook_executions')
    op.drop_index('ix_playbook_executions_id', table_name='playbook_executions')
    op.drop_table('playbook_executions')
    op.drop_index('ix_compliance_controls_id', table_name='compliance_controls')
    op.drop_index('ix_compliance_controls_control_id', table_name='compliance_controls')
    op.drop_index('ix_compliance_controls_framework_id', table_name='compliance_controls')
    op.drop_table('compliance_controls')
    op.drop_index('ix_audit_events_action', table_name='audit_events')
    op.drop_index('ix_audit_events_trace_id', table_name='audit_events')
    op.drop_index('ix_audit_events_user_id', table_name='audit_events')
    op.drop_index('ix_audit_events_id', table_name='audit_events')
    op.drop_index('ix_audit_events_tenant_id', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('ix_api_keys_key_hash', table_name='api_keys')
    op.drop_index('ix_api_keys_tenant_id', table_name='api_keys')
    op.drop_index('ix_api_keys_key_prefix', table_name='api_keys')
    op.drop_table('api_keys')
    op.drop_index('ix_webhook_endpoints_tenant_id', table_name='webhook_endpoints')
    op.drop_index('ix_webhook_endpoints_id', table_name='webhook_endpoints')
    op.drop_table('webhook_endpoints')
    op.drop_index('ix_tenant_key_store_id', table_name='tenant_key_store')
    op.drop_index('ix_tenant_key_store_tenant_id', table_name='tenant_key_store')
    op.drop_table('tenant_key_store')
    op.drop_index('ix_playbooks_name', table_name='playbooks')
    op.drop_index('ix_playbooks_tenant_id', table_name='playbooks')
    op.drop_index('ix_playbooks_id', table_name='playbooks')
    op.drop_table('playbooks')
    op.drop_index('ix_notification_preferences_id', table_name='notification_preferences')
    op.drop_index('ix_notification_preferences_tenant_id', table_name='notification_preferences')
    op.drop_table('notification_preferences')
    op.drop_index('ix_notification_history_tenant_id', table_name='notification_history')
    op.drop_index('ix_notification_history_id', table_name='notification_history')
    op.drop_table('notification_history')
    op.drop_index('ix_intelligence_metrics_metric_name', table_name='intelligence_metrics')
    op.drop_index('ix_intelligence_metrics_id', table_name='intelligence_metrics')
    op.drop_index('ix_intelligence_metrics_tenant_id', table_name='intelligence_metrics')
    op.drop_table('intelligence_metrics')
    op.drop_index('ix_compliance_frameworks_id', table_name='compliance_frameworks')
    op.drop_index('ix_compliance_frameworks_name', table_name='compliance_frameworks')
    op.drop_index('ix_compliance_frameworks_tenant_id', table_name='compliance_frameworks')
    op.drop_table('compliance_frameworks')
