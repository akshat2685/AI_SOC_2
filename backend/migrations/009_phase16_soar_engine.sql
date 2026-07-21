CREATE TABLE playbooks (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    definition JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_playbooks_tenant_id ON playbooks(tenant_id);
CREATE INDEX ix_playbooks_name ON playbooks(name);

CREATE TABLE playbook_executions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    playbook_id INTEGER NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'PENDING',
    context_data JSONB DEFAULT '{}'::jsonb,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_playbook_executions_tenant_id ON playbook_executions(tenant_id);
CREATE INDEX ix_playbook_executions_playbook_id ON playbook_executions(playbook_id);

CREATE TABLE approval_requests (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    execution_id INTEGER NOT NULL REFERENCES playbook_executions(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'PENDING',
    requester_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    approver_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_approval_requests_tenant_id ON approval_requests(tenant_id);
CREATE INDEX ix_approval_requests_execution_id ON approval_requests(execution_id);
