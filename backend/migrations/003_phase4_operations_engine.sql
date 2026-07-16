-- ==============================================================================
-- PHASE 4: AUTONOMOUS SOC OPERATIONS ENGINE
-- ==============================================================================

-- 1. Incident Memory Learning System
CREATE TABLE IF NOT EXISTS incident_memory (
    incident_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attack_type VARCHAR(100) NOT NULL,
    attack_pattern TEXT,
    affected_assets JSONB NOT NULL,
    root_cause TEXT,
    response_taken JSONB,
    success BOOLEAN,
    lessons_learned TEXT,
    confidence FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_incident_memory_attack_type ON incident_memory(attack_type);

-- 2. Human-in-the-Loop Control System (Approvals)
CREATE TABLE IF NOT EXISTS action_approvals (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incident_memory(incident_id),
    action_type VARCHAR(100) NOT NULL,
    reason TEXT NOT NULL,
    evidence JSONB NOT NULL,
    risk_score INTEGER NOT NULL,
    confidence FLOAT NOT NULL,
    required_level INTEGER NOT NULL, -- 0: Info, 1: Auto, 2: Analyst, 3: Manager
    status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED, EXECUTED
    reviewed_by VARCHAR(100),
    review_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON action_approvals(status);

-- 3. SOAR Action Registry
CREATE TABLE IF NOT EXISTS soar_action_registry (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connector_type VARCHAR(50) NOT NULL, -- FIREWALL, ENDPOINT, IDENTITY, TICKET
    capability VARCHAR(100) NOT NULL,
    payload_schema JSONB NOT NULL,
    rollback_supported BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE
);

-- 4. Agent Execution Tracing & Observability
CREATE TABLE IF NOT EXISTS agent_execution_traces (
    trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID,
    agent_name VARCHAR(100) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    latency_ms INTEGER,
    token_usage INTEGER,
    status VARCHAR(50),
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_traces_incident ON agent_execution_traces(incident_id);
