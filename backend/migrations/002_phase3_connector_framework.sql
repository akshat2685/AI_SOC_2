-- ==============================================================================
-- PHASE 3: UNIFIED CONNECTOR FRAMEWORK & CORRELATION ENGINE
-- ==============================================================================

-- 1. Connector Management
CREATE TABLE IF NOT EXISTS connectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL, -- SIEM, EDR, FIREWALL, IAM, CLOUD, EMAIL
    vendor VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'DISCONNECTED',
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS connector_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id UUID REFERENCES connectors(id) ON DELETE CASCADE,
    credential_type VARCHAR(50) NOT NULL, -- API_KEY, OAUTH, BASIC
    encrypted_secret TEXT NOT NULL,
    rotation_policy JSONB DEFAULT '{}',
    last_rotated TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS connector_health (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id UUID REFERENCES connectors(id) ON DELETE CASCADE,
    latency_ms INTEGER,
    last_sync TIMESTAMP WITH TIME ZONE,
    error_count INTEGER DEFAULT 0,
    status_message TEXT
);

-- 2. Unified Event Normalization
CREATE TABLE IF NOT EXISTS normalized_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(100) NOT NULL,
    connector_id UUID REFERENCES connectors(id),
    original_source VARCHAR(255),
    event_type VARCHAR(100),
    severity VARCHAR(50),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    raw_payload JSONB NOT NULL,
    normalized_payload JSONB NOT NULL,
    mitre_techniques TEXT[]
);

CREATE INDEX IF NOT EXISTS idx_normalized_events_timestamp ON normalized_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_normalized_events_type ON normalized_events(event_type);
CREATE INDEX IF NOT EXISTS idx_normalized_events_tenant ON normalized_events(tenant_id);

-- 3. IOC Store
CREATE TABLE IF NOT EXISTS ioc_store (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    value VARCHAR(255) NOT NULL UNIQUE,
    ioc_type VARCHAR(50) NOT NULL, -- IP, DOMAIN, HASH, EMAIL
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    threat_score INTEGER DEFAULT 0,
    related_events UUID[]
);

CREATE INDEX IF NOT EXISTS idx_ioc_value ON ioc_store(value);

-- 4. Correlation & Detection
CREATE TABLE IF NOT EXISTS correlation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name VARCHAR(255) NOT NULL,
    confidence FLOAT NOT NULL,
    correlated_events UUID[] NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. SOAR Playbooks
CREATE TABLE IF NOT EXISTS playbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    trigger_conditions JSONB,
    execution_steps JSONB NOT NULL,
    requires_approval BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS connector_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_id UUID REFERENCES connectors(id),
    level VARCHAR(20),
    message TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
