# ShieldAI (EDYSOR) — Comprehensive End-to-End Testing Plan

> **Scope:** Deep, cross-platform (Windows, macOS, Linux, Cloud) end-to-end verification of every function, service, and integration in the ShieldAI / EDYSOR autonomous SOC platform. This plan is the authoritative reference for validating production readiness following the resolution of audit findings C1–C4, H1–H5, M1–M7, and L1–L4.

---

## 1. Objectives & Exit Criteria

### 1.1 Objectives
- Verify **every function** across all 17+ microservices behaves correctly in isolation and in concert.
- Prove the platform runs and behaves identically on **Windows, macOS, Linux, and Cloud (Kubernetes)**.
- Validate all audit remediations (C1–C4, H1–H5, M1–M7, L1–L4) with dedicated regression tests.
- Confirm resilience, security, performance, and data integrity under realistic and adversarial conditions.

### 1.2 Definition of Done (Exit Criteria)
| Gate | Threshold |
|------|-----------|
| Unit test pass rate | 100% (0 skipped without documented waiver) |
| Line coverage (`backend/app`, `intelligence_engine`) | ≥ 85% |
| Integration test pass rate | 100% |
| E2E scenario pass rate | 100% on all 4 platforms |
| Critical/High security findings | 0 open |
| P95 API latency | ≤ 300 ms under nominal load |
| Chaos/recovery scenarios | 100% auto-recover within SLO |
| Cross-platform smoke suite | Green on Windows, macOS, Linux, Cloud |

---

## 2. Test Pyramid & Taxonomy

```
                 ┌─────────────────────────┐
                 │   Manual / Exploratory   │  (UX, red-team, chaos)
                 ├─────────────────────────┤
                 │   E2E / System (cross-OS)│  full-stack scenarios
                 ├─────────────────────────┤
                 │   Integration            │  service-to-service, DB, Kafka
                 ├─────────────────────────┤
                 │   Component / Contract    │  connectors, agents, API
                 ├─────────────────────────┤
                 │   Unit (largest layer)   │  functions, pure logic
                 └─────────────────────────┘
```

| Layer | Location | Runner | Frequency |
|-------|----------|--------|-----------|
| Unit | `tests/unit`, `tests/test_*.py` | pytest | Every commit |
| API/Contract | `tests/api` | pytest + httpx | Every commit |
| Integration | `tests/integration` | pytest + docker-compose | Every PR |
| Security | `tests/security` | pytest + bandit/trivy | Every PR |
| E2E | `test-e2e.mjs`, `tests/*_e2e.py` | node + pytest | Nightly + release |
| Cross-platform | CI matrix | GitHub Actions | Nightly + release |
| Performance/Chaos | `load_test_results`, k6/locust | scheduled | Weekly + release |

---

## 3. Environments & Platform Matrix

### 3.1 Platform Matrix
| Platform | Runtime target | Purpose | CI runner |
|----------|---------------|---------|-----------|
| **Linux** | Ubuntu 22.04 / 24.04 | Primary dev + prod parity | `ubuntu-latest` |
| **macOS** | macOS 13/14 (Intel + Apple Silicon) | Dev workstation parity | `macos-latest` |
| **Windows** | Windows 11 + WSL2 + native | Dev workstation parity | `windows-latest` |
| **Cloud** | Kubernetes (EKS/GKE/AKS) + Istio | Production topology | self-hosted / ephemeral cluster |

### 3.2 Per-platform concerns to explicitly test
- **Windows:** path separators, CRLF line endings, `deploy.sh` under WSL vs Git Bash, Docker Desktop networking, volume mounts, file locking on ClickHouse/SQLite.
- **macOS:** Apple Silicon (arm64) image availability for all 17 containers, Docker Desktop resource limits, case-insensitive filesystem collisions.
- **Linux:** cgroup limits, systemd service units, SELinux/AppArmor contexts, native package installs.
- **Cloud:** Helm/k8s manifests (`k8s/`, `kubernetes/`), Istio (`istio-1.22.1`) mTLS, Kong (`kong/`) gateway, HPA autoscaling, node failover, cloud secret managers (Vault), managed object store (S3).

### 3.3 Environment tiers
- **Local:** `docker-compose.yml` — full stack on one host.
- **CI ephemeral:** service containers per job.
- **Staging:** `docker-compose.prod.yml` / k8s namespace — mirrors prod, staged deploy pipeline.
- **Production canary:** post-deploy smoke + health checks with automated rollback.

---

## 4. Component-Level Test Coverage (every function)

### 4.1 FastAPI Backend (`backend/`, `app/`)
- **API endpoints** (`tests/api`): every route — auth, incidents, alerts, playbooks, evidence, tenant admin, health/readiness. Positive, negative, boundary, auth-required, and malformed-payload cases per endpoint.
- **Rate limiting (H, Redis-backed):** verify per-key/per-tenant limits, `429` responses, `Retry-After` headers, Redis failover fallback behavior, distributed limit consistency across replicas.
- **API key auth (`test_api_keys.py`):** issuance, rotation, revocation, scope enforcement, expired-key rejection.
- **Structured logging (`test_logging.py`):** JSON schema, correlation IDs, no secret leakage in logs.
- **Migrations (`test_migrations.py`):** Alembic up/down, idempotency, schema drift detection.
- **Multi-tenant isolation (`test_multi_tenant.py`):** cross-tenant data leakage prevention, RLS/scoping on every query path.

### 4.2 LangGraph AI Agents (`intelligence_engine/`, agent prompts)
Test each agent's graph nodes, tool calls, and output contracts:
- **Supervisor** — routing/delegation correctness, loop termination, guardrail enforcement.
- **Triage Analyst** — alert enrichment, severity scoring, dedup.
- **Threat Intel Agent** — IOC lookup, feed integration (mocked), enrichment accuracy.
- **Response Coordinator** — playbook selection, action ordering, human-in-the-loop gates.
- **Purple Team Orchestrator** — simulation orchestration (`simulate_attacks.py`).
- **Playbook RL Optimizer** — reward signal, policy update, no-regression on known playbooks.
- **Contract tests:** every LLM output validated against Pydantic schemas (invalid/hallucinated output rejected & retried). Guardrails (`guardrails/`) block unsafe tool invocations.
- **Determinism:** seed/temperature-controlled runs; snapshot golden traces.
- **Memory/learning (`test_memory_learning.py`):** write/read, decay, retrieval relevance.

### 4.3 Detection & Automation Engines
- **Detection engine (`test_detection_engine.py`, `test_detect.py`):** rule matching, threshold logic, false-positive/negative bounds against labeled dataset.
- **Automation/SOAR engine (`test_soar_engine.py`, `test_soar_engine_e2e.py`, `test_automation_engine.py`):** playbook execution, async policy execution, step retries, rollback on failure, idempotency, concurrent playbook safety.
- **Plugins & graph (`test_plugins_soar_graph.py`):** plugin loading, sandboxing, graph traversal.

### 4.4 Connectors (audit H — real implementations)
For **Firewall**, **Ticket**, and **PlaybookRecommender** connectors:
- Contract tests against mocked upstreams (block IP, unblock, create/update/close ticket, recommend playbook).
- Failure injection: upstream 5xx, timeout, malformed response → verify retry/backoff/DLQ.
- Auth/credential handling via Vault (no plaintext secrets).
- Idempotency keys to prevent duplicate firewall rules / tickets.

### 4.5 Event Streaming — Kafka (audit C — real event bus + DLQ)
- Produce/consume round-trip for every topic.
- **DLQ:** malformed/poison messages routed to DLQ; replay from DLQ works.
- Consumer group rebalance, at-least-once delivery, offset commit correctness.
- Ordering guarantees per partition key.
- Backpressure under burst load.

### 4.6 Data Stores
- **Neo4j:** graph writes/reads, relationship integrity, `test-neo4j*` ping/health, query performance on large graphs, index usage.
- **ClickHouse (audit M — audit sink):** insert throughput, lock safety (`tests/integration`), query correctness, retention/TTL, `test_audit_logging.py`.
- **Native/storage engine (`test_native_storage_engine.py`):** CRUD, concurrency, corruption recovery.
- **Cache/Redis (`cache/`):** TTL, eviction, rate-limit counters, session store.
- **Migrations & data integrity:** referential integrity across stores after migration.

### 4.7 Secrets — Vault (audit C — production config)
- `test_secrets_management.py`: secret read, dynamic secrets, lease renewal, rotation.
- Sealed/unsealed states, auth methods, policy enforcement (least privilege).
- App fails closed if Vault unavailable (no plaintext fallback).

### 4.8 Evidence Vault — S3 (audit M)
- Upload/download evidence, integrity hash verification, immutability/WORM, presigned URL expiry, encryption at rest, access-control per tenant.

### 4.9 Real-time — WebSockets (audit H — heartbeat/reconnect)
- `test-ws.mjs`: connect, auth handshake, message delivery.
- Heartbeat ping/pong, idle timeout, automatic reconnect with backoff, message replay after reconnect, connection storm handling.

### 4.10 Frontend (`frontend/`)
- Component unit tests, routing, auth flows, incident dashboard rendering.
- WebSocket live updates reflected in UI.
- Cross-browser (Chromium, Firefox, WebKit) via Playwright.
- Accessibility (axe) and responsive layout smoke.

### 4.11 Gateway & Service Mesh (Cloud)
- Kong routing, rate-limit plugin, auth plugin.
- Istio mTLS between services, traffic policies, retries/timeouts, fault injection.

---

## 5. End-to-End Scenarios (full-stack, cross-platform)

Each scenario runs on **all four platforms**. `test-e2e.mjs` and `tests/*_e2e.py` are the harnesses.

| ID | Scenario | Path exercised |
|----|----------|----------------|
| E2E-01 | **Alert → Triage → Incident** | Ingest event → Kafka → detection engine → Triage agent → incident created → WebSocket push to UI |
| E2E-02 | **Autonomous response** | Incident → Supervisor → Response Coordinator → Firewall connector blocks IP → Ticket connector opens ticket → audit to ClickHouse |
| E2E-03 | **Human-in-the-loop approval** | High-severity action gated → analyst approves in UI → action executes → evidence to S3 |
| E2E-04 | **Threat intel enrichment** | IOC arrives → Threat Intel agent enriches via Neo4j graph → severity upgraded |
| E2E-05 | **Playbook recommendation + RL** | PlaybookRecommender suggests → executed → outcome feeds RL optimizer |
| E2E-06 | **Digital twin simulation** (`test_digital_twin_e2e.py`) | Simulated attack (`simulate_attacks.py`) → Purple Team orchestrator → detection validated |
| E2E-07 | **Failure & DLQ recovery** | Poison event → DLQ → replay → correct processing |
| E2E-08 | **Multi-tenant isolation** | Two tenants act concurrently → verify zero cross-tenant leakage end to end |
| E2E-09 | **Full audit trail** | Any action → immutable audit record in ClickHouse + evidence in S3, tamper-evident |
| E2E-10 | **Login → session → logout** (`test-login.mjs`) | Auth lifecycle incl. token expiry & refresh |

---

## 6. Non-Functional Testing

### 6.1 Performance & Load
- Baseline & soak load with k6/locust; extend `load_test_results.txt` / `health_load_test.txt`.
- Targets: P95 API ≤ 300 ms; Kafka sustained ≥ target msg/s; detection latency SLO; agent decision latency SLO.
- Autoscaling (HPA) verification in Cloud; scale-up/down under load.

### 6.2 Resilience / Chaos
- Kill each container/pod → verify auto-recovery, no data loss, DLQ intact.
- Network partition between services (Istio fault injection).
- Dependency outage: Vault down, Redis down, Neo4j down, Kafka broker loss → fail-closed / graceful degradation.
- Staged-deploy rollback drill: bad release → health check fails → automatic rollback (validate `deploy.yml`, `rollback_plan.md`).

### 6.3 Security
- **SAST/deps:** bandit, trivy, `security.yml` workflow, dependency audit.
- **Secrets scanning:** no secrets in repo/images (secret scanning tool).
- **AuthN/Z:** RBAC, API key scopes, tenant boundaries, JWT tampering.
- **Injection/abuse:** prompt injection against agents, SQL/Cypher injection, SSRF via connectors.
- **DAST:** OWASP ZAP against staging.
- **Rate-limit abuse & DoS** protections.
- Container/image hardening, non-root, read-only FS where possible.

### 6.4 Data Integrity & DR
- Backup/restore for each datastore.
- Migration forward/rollback with production-like data volume.
- RPO/RTO validation from `rollback_plan.md` / `operations_runbook.md`.

---

## 7. CI/CD Integration

Extend existing workflows (`ci.yml`, `test.yml`, `build.yml`, `deploy.yml`, `security.yml`, `evaluate.yml`):

1. **Per-commit:** lint, type-check, unit + API tests, coverage gate (Python 3.11 pinned).
2. **Per-PR:** integration + security tests, image build + trivy scan.
3. **Nightly:** full E2E on **cross-platform matrix** (ubuntu/macos/windows) + ephemeral k8s Cloud run.
4. **Release:** performance + chaos + DAST + DR drill → staged deploy → canary smoke → auto-rollback on failure.
5. **Agent evaluation (`evaluate.yml`):** golden-trace regression + guardrail assertions.

```yaml
# Cross-platform matrix (illustrative)
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python: ['3.11']
```

---

## 8. Test Data & Fixtures
- Deterministic seed datasets for detection (labeled true/false positives).
- Mocked upstreams for all external connectors (firewall API, ticketing, TI feeds, LLM).
- Golden traces for agent outputs (snapshot testing).
- Synthetic multi-tenant fixtures.
- Attack corpus via `simulate_attacks.py` for repeatable red-team runs.
- All fixtures centralized in `tests/conftest.py`; no live credentials — Vault stub in test mode.

---

## 9. Traceability — Audit Findings → Tests

| Finding | Remediation | Verifying test(s) |
|---------|-------------|-------------------|
| C1–C4 | Kafka event bus + DLQ, Vault prod config | §4.5, §4.7, E2E-07, chaos §6.2 |
| H1–H5 | Redis rate limiting, real connectors, WS heartbeat | §4.1, §4.4, §4.9, E2E-02/03 |
| M1–M7 | ClickHouse audit sink, S3 evidence vault, docs | §4.6, §4.8, E2E-09 |
| L1–L4 | CI py3.11 pin, test-exclusion removal, cosmetic | §7, coverage gate, lint |
| Skipped tests | Un-skipped in suite | 0 skipped gate (§1.2) |
| Feature gaps | Full staged deploy + health/rollback | §6.2 rollback drill, §7 release |

Every finding ID must map to at least one automated test before release sign-off.

---

## 10. Roles, Cadence & Reporting
- **Owners:** Backend, AI/Agents, Platform/SRE, Security leads each own their §4 area.
- **Cadence:** unit/API every commit; integration/security every PR; E2E + cross-platform nightly; perf/chaos/DR weekly + release.
- **Reporting:** coverage + pass-rate dashboard, per-platform matrix status, security findings tracker, release readiness checklist (`production_checklist.md`).
- **Sign-off:** all §1.2 gates green on all four platforms + zero open critical/high findings.

---

## 11. Execution Quick Reference

```bash
# Full suite + coverage
python -m pytest tests/ -v --cov=backend/app --cov=intelligence_engine --cov-report=term-missing

# Layer-scoped
python -m pytest tests/unit tests/api          # fast feedback
python -m pytest tests/integration tests/security

# E2E (requires full stack up)
docker compose up -d
node test-e2e.mjs
python -m pytest tests/test_soar_engine_e2e.py tests/test_digital_twin_e2e.py -v

# Attack simulation
python simulate_attacks.py
```
