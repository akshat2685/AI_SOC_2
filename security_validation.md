# ShieldAI Security Validation

**Last updated:** 2025-01-01  
**Stack:** FastAPI (Python 3.11), slowapi, aiokafka, SQLAlchemy, Vault AppRole

> This document is generated from the actual code paths. Every control listed here maps to a real implementation; stale entries are removed each release.

---

## 1. Transport Security

| Control | Implementation | File |
|---------|---------------|------|
| TLS for all external endpoints | FastAPI behind TLS-terminating reverse proxy (nginx/traefik) | `docker-compose.prod.yml` → `vault-config.hcl` listener |
| Vault TLS | `tls_cert_file` / `tls_key_file` in Vault config; TLS 1.2+ enforced | `vault/vault-config.hcl` |
| HSTS, X-Frame-Options, X-Content-Type | Security headers middleware applied to all responses | `backend/app/main.py` |

## 2. Authentication & Authorization

| Control | Implementation | File |
|---------|---------------|------|
| JWT bearer token auth | FastAPI `Depends` on `get_current_user`; tokens validated on every protected route | `backend/app/api/deps.py` |
| Multi-tenant Row-Level Security | PostgreSQL RLS via `set_config('rls.tenant_id', ...)` — enforced on all DB sessions | `backend/app/infrastructure/audit_consumer.py` |
| Vault AppRole (no root token) | Services authenticate to Vault with `role_id`/`secret_id` injected at deploy; root token NOT present in code | `vault/vault-config.hcl`, `docker-compose.prod.yml` |

## 3. Rate Limiting

| Control | Implementation | File |
|---------|---------------|------|
| Shared rate limiting (multi-replica) | `slowapi` with Redis backend (`RATE_LIMIT_STORAGE_URI=redis://...`); 100 req/min default | `backend/app/api/middleware/rate_limit_middleware.py` |
| 429 response with `retry_after` | Custom `_rate_limit_exceeded_handler` returns structured JSON | same file |

## 4. Input Validation

| Control | Implementation | File |
|---------|---------------|------|
| Request body validation | Pydantic v2 models on all API request schemas; automatic 422 on invalid input | `backend/app/api/v1/` |
| SQL injection prevention | SQLAlchemy ORM + parameterized queries; raw `text()` calls use `:param` bindings | `backend/app/infrastructure/` |
| SSRF / path traversal | Connector URLs sourced from env/Vault, never from user input | `intelligence_engine/soar/connectors/` |

## 5. Secret Management

| Control | Implementation | File |
|---------|---------------|------|
| No secrets in code or environment files | All credentials fetched from Vault at runtime | `backend/app/core/config.py` |
| Audit secret key (HMAC) | `AUDIT_SECRET_KEY` from Vault; used for chain-of-custody hashing | `backend/app/infrastructure/audit_consumer.py` |

## 6. Audit & Compliance

| Control | Implementation | File |
|---------|---------------|------|
| HMAC chain-of-custody | Every audit event hashed with `HMAC-SHA256(prev_hash + event)` per tenant | `backend/app/infrastructure/audit_consumer.py` |
| ClickHouse audit sink | Events batch-written to ClickHouse with DLQ for failed batches | same file |
| Evidence immutability | S3 Object Lock (COMPLIANCE mode, 7-year retention) + SHA-256 hash | `intelligence_engine/soar/core/evidence_vault.py` |

## 7. Known Limitations / Accepted Risks

| Item | Status | Mitigation |
|------|--------|-----------|
| Honeypot Cowrie events not yet in Kafka pipeline | Configuration required | Add log→Kafka bridge before production |
| MISP/TAXII threat intel feed | Configuration required | Add feed URLs + Vault creds at deploy |
| WebSocket idle timeout on Cloud Run | L3 — client heartbeat implemented | Document Cloud Run `--timeout` setting |

---

*This document must be reviewed and updated with every release. Out-of-date security docs are treated as a finding.*
