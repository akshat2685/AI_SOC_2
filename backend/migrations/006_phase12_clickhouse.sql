-- ClickHouse DDL for Immutable Audit Logging
CREATE TABLE IF NOT EXISTS audit_log (
    tenant_id UInt32,
    user_id Nullable(UInt32),
    trace_id String,
    action String,
    details String,
    integrity_hash String,
    timestamp DateTime64(3, 'UTC') DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (tenant_id, timestamp, action);
