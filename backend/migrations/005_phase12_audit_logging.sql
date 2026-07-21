-- PostgreSQL Audit Log Migration
CREATE TABLE audit_events (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    trace_id VARCHAR(255),
    action VARCHAR(255) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    integrity_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_audit_events_tenant_id ON audit_events(tenant_id);
CREATE INDEX ix_audit_events_action ON audit_events(action);

-- Enable RLS
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- Create RLS Policy
CREATE POLICY isolate_audit_events 
ON audit_events 
FOR ALL
USING (tenant_id = current_setting('rls.tenant_id', true)::int);

-- Revoke mutating operations from the app role (using public as placeholder for app connection role)
REVOKE UPDATE, DELETE ON audit_events FROM public;
