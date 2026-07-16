-- ==============================================================================
-- AI SOC INTELLIGENCE ENGINE (EDYSOR-X) - PHASE 2 MIGRATION
-- Tables for Autonomous Investigation, Memory, and Telemetry
-- ==============================================================================

-- 1. SECURITY EVENTS (Normalized Telemetry Layer)
CREATE TABLE IF NOT EXISTS security_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(255) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    entity VARCHAR(255),
    event_type VARCHAR(100) NOT NULL,
    raw_data JSONB NOT NULL,
    threat_score FLOAT DEFAULT 0.0
);
CREATE INDEX idx_security_events_timestamp ON security_events(timestamp);
CREATE INDEX idx_security_events_entity ON security_events(entity);
CREATE INDEX idx_security_events_severity ON security_events(severity);
-- O(log n) lookup for raw json attributes via GIN
CREATE INDEX idx_security_events_raw_data ON security_events USING GIN (raw_data);

-- 2. INVESTIGATIONS (Autonomous Planner Output)
CREATE TABLE IF NOT EXISTS investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'IN_PROGRESS',
    hypothesis TEXT,
    confidence_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recommended_action VARCHAR(255)
);
CREATE INDEX idx_investigations_alert_id ON investigations(alert_id);
CREATE INDEX idx_investigations_status ON investigations(status);

-- 3. INVESTIGATION STEPS (Evidence Collection & Timeline)
CREATE TABLE IF NOT EXISTS investigation_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id) ON DELETE CASCADE,
    agent_role VARCHAR(100) NOT NULL,
    step_description TEXT NOT NULL,
    evidence_collected JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_investigation_steps_inv_id ON investigation_steps(investigation_id);

-- 4. AGENT DECISIONS (Security Reasoning Engine Audit)
CREATE TABLE IF NOT EXISTS agent_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id) ON DELETE CASCADE,
    observation TEXT,
    evidence_references JSONB,
    mitre_mapping JSONB,
    risk_score INT,
    decision_taken TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agent_decisions_inv_id ON agent_decisions(investigation_id);

-- 5. RESPONSE ACTIONS (SOAR Automation Framework)
CREATE TABLE IF NOT EXISTS response_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id),
    action_type VARCHAR(100) NOT NULL,
    target_entity VARCHAR(255),
    risk_level VARCHAR(50) NOT NULL, -- Low, Medium, High
    approval_status VARCHAR(50) DEFAULT 'PENDING',
    executed_at TIMESTAMPTZ,
    result TEXT
);
CREATE INDEX idx_response_actions_status ON response_actions(approval_status);

-- 6. MEMORY FEEDBACK (SOC Experience Replay Memory)
CREATE TABLE IF NOT EXISTS memory_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event JSONB NOT NULL,
    decision JSONB NOT NULL,
    reasoning TEXT,
    confidence FLOAT,
    outcome VARCHAR(50),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_memory_feedback_outcome ON memory_feedback(outcome);

-- 7. ANALYST FEEDBACK (RLHF / Continuous Learning)
CREATE TABLE IF NOT EXISTS analyst_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id),
    analyst_id VARCHAR(255) NOT NULL,
    feedback_type VARCHAR(50), -- True Positive, False Positive, Ignored
    comments TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_analyst_feedback_type ON analyst_feedback(feedback_type);
