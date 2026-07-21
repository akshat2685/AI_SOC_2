ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_api_keys ON api_keys
    USING (tenant_id = current_setting('rls.tenant_id')::int);

ALTER TABLE tenant_key_store ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_key_store ON tenant_key_store
    USING (tenant_id = current_setting('rls.tenant_id')::int);
