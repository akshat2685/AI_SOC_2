CREATE TABLE notification_preferences (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) NOT NULL,
    channel VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    min_severity VARCHAR(50) DEFAULT 'LOW',
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    config JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE webhook_endpoints (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) NOT NULL,
    url VARCHAR(1024) NOT NULL,
    secret VARCHAR(2048) NOT NULL,
    events JSONB DEFAULT '[]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE notification_history (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) NOT NULL,
    channel VARCHAR(50) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    status VARCHAR(50) DEFAULT 'delivered',
    attempts INTEGER DEFAULT 1,
    error TEXT,
    delivered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_notification_preferences ON notification_preferences
    USING (tenant_id = NULLIF(current_setting('rls.tenant_id', TRUE), '')::INTEGER OR current_setting('rls.tenant_id', TRUE) = '');

ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_webhook_endpoints ON webhook_endpoints
    USING (tenant_id = NULLIF(current_setting('rls.tenant_id', TRUE), '')::INTEGER OR current_setting('rls.tenant_id', TRUE) = '');

ALTER TABLE notification_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_notification_history ON notification_history
    USING (tenant_id = NULLIF(current_setting('rls.tenant_id', TRUE), '')::INTEGER OR current_setting('rls.tenant_id', TRUE) = '');
