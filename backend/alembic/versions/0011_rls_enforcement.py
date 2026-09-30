"""Alembic migration 0011: enforce real Row-Level Security on tenant tables.

Background: backend/migrations/004_phase10_multi_tenant.sql defined RLS
policies, but nothing ever applied that file — the app runs Alembic only,
and no Alembic version contained any CREATE POLICY. Production tenant
isolation was therefore application-level WHERE clauses only, and several
tables (security_events, device_commands, ...) never had policies at all.

This migration makes RLS real:

- ENABLE + FORCE ROW LEVEL SECURITY on every tenant-scoped table. FORCE
  matters because the app role owns the tables; without FORCE, owners
  bypass RLS entirely.
- One permissive policy per table driven by two session GUCs, set by
  app/infrastructure/storage/context.py:
      rls.app_role   = 'tenant' | 'service'
      rls.tenant_id  = '<tenant id>'            (only when app_role='tenant')
  Policy:  app_role = 'service'  -> full access (privileged code paths only:
             login, register, API-key resolution, seeding, background loops)
           app_role = 'tenant'   -> only rows whose tenant_id matches
  When neither GUC is set the policy evaluates to NULL -> no rows
  (default-deny). There is deliberately NO empty-string bypass.
- `users.tenant_id` is nullable (global admins); NULL-tenant users are only
  visible in service scope.
- `tenants` itself is scoped by id; `compliance_controls`/`compliance_rules`
  (no direct tenant_id) are scoped through their framework.

Downgrade drops the policies and disables RLS again.
"""

revision = "0011_rls_enforcement"
down_revision = "0010_twin_scenarios"
branch_labels = None
depends_on = None

# Tables carrying their own tenant_id column.
_TENANT_TABLES = [
    "users",
    "assets",
    "incidents",
    "alerts",
    "detection_watermarks",
    "api_keys",
    "audit_events",
    "notification_preferences",
    "webhook_endpoints",
    "notification_history",
    "tenant_key_store",
    "intelligence_metrics",
    "playbooks",
    "playbook_executions",
    "approval_requests",
    "compliance_frameworks",
    "compliance_violations",
    "integrations",
    "endpoint_agents",
    "onboarding_state",
    "security_events",
    "training_feedback",
    "device_commands",
]

_ROLE_CHECK = "current_setting('rls.app_role', true) = 'service'"
_TENANT_CHECK = "NULLIF(current_setting('rls.tenant_id', true), '')"


def _policy_sql(table: str, expr: str) -> str:
    return (
        f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";\n'
        f'CREATE POLICY tenant_isolation ON "{table}" FOR ALL\n'
        f"  USING ({expr})\n"
        f"  WITH CHECK ({expr});"
    )


def _direct_expr() -> str:
    # tenant_id present and equal; NULL tenant_id rows are service-only.
    return (
        f"{_ROLE_CHECK} OR "
        f"(tenant_id IS NOT NULL AND tenant_id::text = {_TENANT_CHECK})"
    )


def upgrade():
    from alembic import op

    # Drop the dead policies from backend/migrations/004 (never applied by
    # the app, but harmless to be idempotent if someone applied them by hand).
    for old in (
        "tenant_isolation_users",
        "tenant_isolation_assets",
        "tenant_isolation_incidents",
        "tenant_isolation_alerts",
    ):
        op.execute(f'DROP POLICY IF EXISTS "{old}" ON "{old.split("_", 2)[2]}";')

    stmts = []
    for table in _TENANT_TABLES:
        stmts.append(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        stmts.append(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
        stmts.append(_policy_sql(table, _direct_expr()))

    # tenants: scoped by its own id.
    stmts.append('ALTER TABLE "tenants" ENABLE ROW LEVEL SECURITY;')
    stmts.append('ALTER TABLE "tenants" FORCE ROW LEVEL SECURITY;')
    stmts.append(
        _policy_sql(
            "tenants",
            f"{_ROLE_CHECK} OR (id::text = {_TENANT_CHECK})",
        )
    )

    # compliance_controls -> framework -> tenant.
    stmts.append('ALTER TABLE "compliance_controls" ENABLE ROW LEVEL SECURITY;')
    stmts.append('ALTER TABLE "compliance_controls" FORCE ROW LEVEL SECURITY;')
    stmts.append(
        _policy_sql(
            "compliance_controls",
            f"""{_ROLE_CHECK} OR EXISTS (
                   SELECT 1 FROM compliance_frameworks f
                   WHERE f.id = compliance_controls.framework_id
                     AND f.tenant_id IS NOT NULL
                     AND f.tenant_id::text = {_TENANT_CHECK}
                 )""",
        )
    )

    # compliance_rules -> control -> framework -> tenant.
    stmts.append('ALTER TABLE "compliance_rules" ENABLE ROW LEVEL SECURITY;')
    stmts.append('ALTER TABLE "compliance_rules" FORCE ROW LEVEL SECURITY;')
    stmts.append(
        _policy_sql(
            "compliance_rules",
            f"""{_ROLE_CHECK} OR EXISTS (
                   SELECT 1 FROM compliance_controls c
                   JOIN compliance_frameworks f ON f.id = c.framework_id
                   WHERE c.id = compliance_rules.control_id
                     AND f.tenant_id IS NOT NULL
                     AND f.tenant_id::text = {_TENANT_CHECK}
                 )""",
        )
    )

    # audit_events: append-only at the database level too.
    stmts.append("REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC;")

    for s in stmts:
        op.execute(s)


def downgrade():
    from alembic import op

    tables = (
        _TENANT_TABLES
        + ["tenants", "compliance_controls", "compliance_rules"]
    )
    for table in tables:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}";')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')
    op.execute("GRANT UPDATE, DELETE ON audit_events TO PUBLIC;")
