CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) NOT NULL,
    hostname VARCHAR(255) NOT NULL,
    ip_address VARCHAR(50) NOT NULL,
    asset_type VARCHAR(100) NOT NULL,
    criticality VARCHAR(50) DEFAULT 'MEDIUM' NOT NULL
);

ALTER TABLE incidents ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) NOT NULL;
ALTER TABLE alerts ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) NOT NULL;

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

-- Define RLS Policies
-- current_setting('rls.tenant_id', TRUE) returns the local setting. If it's an empty string '', we treat it as Global Admin access (see BaseRepository._set_rls).
CREATE POLICY tenant_isolation_users ON users
    USING (tenant_id = NULLIF(current_setting('rls.tenant_id', TRUE), '')::INTEGER OR current_setting('rls.tenant_id', TRUE) = '');

CREATE POLICY tenant_isolation_assets ON assets
    USING (tenant_id = NULLIF(current_setting('rls.tenant_id', TRUE), '')::INTEGER OR current_setting('rls.tenant_id', TRUE) = '');

CREATE POLICY tenant_isolation_incidents ON incidents
    USING (tenant_id = NULLIF(current_setting('rls.tenant_id', TRUE), '')::INTEGER OR current_setting('rls.tenant_id', TRUE) = '');

CREATE POLICY tenant_isolation_alerts ON alerts
    USING (tenant_id = NULLIF(current_setting('rls.tenant_id', TRUE), '')::INTEGER OR current_setting('rls.tenant_id', TRUE) = '');
