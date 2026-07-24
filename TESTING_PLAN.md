# ShieldAI (EDYSOR) — Comprehensive End-to-End Testing Plan

> **Scope:** Deep, cross-platform (Windows, macOS, Linux, Cloud) end-to-end verification of every function, service, and integration in the ShieldAI / EDYSOR autonomous SOC platform. This plan is the authoritative reference for validating production readiness following the resolution of audit findings C1–C4, H1–H5, M1–M7, and L1–L4.

> **How to read this document:** §0 is the live implementation-status tracker — it tells you what is already committed to `main` and what is still outstanding. §1–§11 are the standing plan. §12–§18 are the **concrete, file-path-level specifications** for every test suite that still needs to be implemented, plus the two CI workflow changes that must be applied by hand (the GitHub integration cannot write `.github/workflows/*`).

---

## 0. Implementation Status Tracker

Legend: ✅ committed to `main` · 🟡 partial · ⛔ blocked (needs manual action) · ⬜ not started

### 0.1 Already implemented and committed
| Item | Location | Status |
|------|----------|--------|
| PlaybookRecommender golden-trace snapshot tests | `tests/test_playbook_recommender_golden.py` + 2 golden snapshot files | ✅ |
| Connector retry / failure-injection tests | `tests/test_connectors_retry.py` | ✅ |
| Kafka DLQ routing + replay tests | `tests/test_kafka_dlq.py` | ✅ |
| Audit remediations C1–C4, H1–H5, M1–M7, L1–L4 (Kafka/DLQ, Vault, Redis rate limiting, real connectors, audit/evidence storage, WebSocket resilience, staged deploy/rollback) | across `backend/`, `intelligence_engine/`, `connectors/` | ✅ |

### 0.2 Blocked — needs manual application (workflow write permission)
| Item | Location | Status | Unblock |
|------|----------|--------|---------|
| Cross-platform CI matrix (Ubuntu/macOS/Windows) | `.github/workflows/test.yml` | ⛔ | Apply YAML from **§17** via GitHub web editor, or grant the connector **Workflows: Read and write** |
| Staging chaos/DR rollback release gate | `.github/workflows/deploy.yml` | ⛔ | Apply YAML from **§18** via GitHub web editor |

### 0.3 Outstanding test suites to implement
| Suite | Spec | Status |
|-------|------|--------|
| Docker-backed integration/E2E harness | §12 | ⬜ |
| Cloud / Kubernetes topology tests | §13 | ⬜ |
| Security / DAST / secrets / injection | §14 | ⬜ |
| Performance / load / soak / autoscale | §15 | ⬜ |
| Chaos engineering | §16.1 | ⬜ |
| Disaster recovery (backup/restore, RPO/RTO) | §16.2 | ⬜ |
| Full E2E scenario coverage E2E-01…E2E-10 | §5 + §12 | 🟡 |

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
| DR drill | Restore within RTO, data loss within RPO |
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
- **Determinism:** seed/temperature-controlled runs; snapshot golden traces (✅ `tests/test_playbook_recommender_golden.py`).
- **Memory/learning (`test_memory_learning.py`):** write/read, decay, retrieval relevance.

### 4.3 Detection & Automation Engines
- **Detection engine (`test_detection_engine.py`, `test_detect.py`):** rule matching, threshold logic, false-positive/negative bounds against labeled dataset.
- **Automation/SOAR engine (`test_soar_engine.py`, `test_soar_engine_e2e.py`, `test_automation_engine.py`):** playbook execution, async policy execution, step retries, rollback on failure, idempotency, concurrent playbook safety.
- **Plugins & graph (`test_plugins_soar_graph.py`):** plugin loading, sandboxing, graph traversal.

### 4.4 Connectors (audit H — real implementations)
For **Firewall**, **Ticket**, and **PlaybookRecommender** connectors:
- Contract tests against mocked upstreams (block IP, unblock, create/update/close ticket, recommend playbook).
- Failure injection: upstream 5xx, timeout, malformed response → verify retry/backoff/DLQ (✅ `tests/test_connectors_retry.py`).
- Auth/credential handling via Vault (no plaintext secrets).
- Idempotency keys to prevent duplicate firewall rules / tickets.

### 4.5 Event Streaming — Kafka (audit C — real event bus + DLQ)
- Produce/consume round-trip for every topic.
- **DLQ:** malformed/poison messages routed to DLQ; replay from DLQ works (✅ `tests/test_kafka_dlq.py`).
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

Each scenario runs on **all four platforms**. `test-e2e.mjs` and `tests/*_e2e.py` are the harnesses. Implementation harness is specified in §12.

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
- Full spec in **§15**.

### 6.2 Resilience / Chaos
- Kill each container/pod → verify auto-recovery, no data loss, DLQ intact.
- Network partition between services (Istio fault injection).
- Dependency outage: Vault down, Redis down, Neo4j down, Kafka broker loss → fail-closed / graceful degradation.
- Staged-deploy rollback drill: bad release → health check fails → automatic rollback (validate `deploy.yml`, `rollback_plan.md`).
- Full spec in **§16**.

### 6.3 Security
- **SAST/deps:** bandit, trivy, `security.yml` workflow, dependency audit.
- **Secrets scanning:** no secrets in repo/images (secret scanning tool).
- **AuthN/Z:** RBAC, API key scopes, tenant boundaries, JWT tampering.
- **Injection/abuse:** prompt injection against agents, SQL/Cypher injection, SSRF via connectors.
- **DAST:** OWASP ZAP against staging.
- **Rate-limit abuse & DoS** protections.
- Container/image hardening, non-root, read-only FS where possible.
- Full spec in **§14**.

### 6.4 Data Integrity & DR
- Backup/restore for each datastore.
- Migration forward/rollback with production-like data volume.
- RPO/RTO validation from `rollback_plan.md` / `operations_runbook.md`.
- Full spec in **§16.2**.

---

## 7. CI/CD Integration

Extend existing workflows (`ci.yml`, `test.yml`, `build.yml`, `deploy.yml`, `security.yml`, `evaluate.yml`):

1. **Per-commit:** lint, type-check, unit + API tests, coverage gate (Python 3.11 pinned).
2. **Per-PR:** integration + security tests, image build + trivy scan.
3. **Nightly:** full E2E on **cross-platform matrix** (ubuntu/macos/windows) + ephemeral k8s Cloud run.
4. **Release:** performance + chaos + DAST + DR drill → staged deploy → canary smoke → auto-rollback on failure.
5. **Agent evaluation (`evaluate.yml`):** golden-trace regression + guardrail assertions.

> ⛔ The matrix change to `test.yml` (§17) and the chaos/DR release gate in `deploy.yml` (§18) are **not yet applied** — the integration lacks workflow write permission. Apply them manually.

---

## 8. Test Data & Fixtures
- Deterministic seed datasets for detection (labeled true/false positives).
- Mocked upstreams for all external connectors (firewall API, ticketing, TI feeds, LLM).
- Golden traces for agent outputs (snapshot testing) — ✅ committed.
- Synthetic multi-tenant fixtures.
- Attack corpus via `simulate_attacks.py` for repeatable red-team runs.
- All fixtures centralized in `tests/conftest.py`; no live credentials — Vault stub in test mode.

---

## 9. Traceability — Audit Findings → Tests

| Finding | Remediation | Verifying test(s) |
|---------|-------------|-------------------|
| C1–C4 | Kafka event bus + DLQ, Vault prod config | §4.5, §4.7, E2E-07, chaos §16 |
| H1–H5 | Redis rate limiting, real connectors, WS heartbeat | §4.1, §4.4, §4.9, E2E-02/03 |
| M1–M7 | ClickHouse audit sink, S3 evidence vault, docs | §4.6, §4.8, E2E-09 |
| L1–L4 | CI py3.11 pin, test-exclusion removal, cosmetic | §7, coverage gate, lint |
| Skipped tests | Un-skipped in suite | 0 skipped gate (§1.2) |
| Feature gaps | Full staged deploy + health/rollback | §16 rollback drill, §7 release |

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

# New suites (see §12–§16)
python -m pytest tests/integration/test_docker_e2e.py -v -m docker
python -m pytest tests/cloud -v -m k8s
python -m pytest tests/security -v
k6 run perf/k6_api_baseline.js
python -m pytest tests/chaos -v -m chaos
python -m pytest tests/dr -v -m dr
```

---

# PART II — Concrete Specifications for Remaining Suites

The following sections are implementation-ready specs for the suites still marked ⬜/🟡 in §0.3. Each lists the target files, markers, fixtures, and the exact cases to implement.

## 12. Docker-backed Integration / E2E Harness

**Goal:** run true full-stack scenarios (E2E-01…E2E-10) against real containers, not mocks.

**Files to create**
- `tests/integration/conftest.py` — session-scoped fixture that boots the stack via `docker compose -f docker-compose.yml up -d`, waits for health endpoints, tears down after.
- `tests/integration/test_docker_e2e.py` — pytest markers `@pytest.mark.docker`, one test per E2E scenario ID.
- `tests/integration/helpers.py` — HTTP/WS/Kafka client helpers + health-wait polling.

**Fixtures / infra**
- `compose_stack` fixture: bring up, poll `/health` + `/ready` on each service with timeout+backoff, `yield`, then `docker compose down -v`.
- Deterministic seed loader that pushes the labeled detection dataset and multi-tenant fixtures before scenarios.
- Ephemeral Vault in dev mode + MinIO as S3 stand-in + single-broker Kafka + Neo4j + ClickHouse + Redis from compose.

**Cases (map 1:1 to §5)**
- `test_e2e01_alert_to_incident` — POST event → assert Kafka topic consumed → detection fires → incident row created → WS client receives push.
- `test_e2e02_autonomous_response` — assert firewall connector called (mock upstream records block) + ticket created + ClickHouse audit row.
- `test_e2e03_hitl_approval` — high-severity action stays `pending_approval`; approve via API; assert executed + S3 evidence object exists with integrity hash.
- `test_e2e04_threat_intel_enrichment` — inject IOC; assert Neo4j relationship written + severity upgraded.
- `test_e2e05_playbook_rl` — recommendation executed; assert RL optimizer received reward event.
- `test_e2e06_digital_twin` — run `simulate_attacks.py`; assert detection coverage report.
- `test_e2e07_dlq_recovery` — publish poison message; assert routed to DLQ; trigger replay; assert processed.
- `test_e2e08_multi_tenant_isolation` — concurrent tenant A/B actions; assert zero cross-reads on every store.
- `test_e2e09_audit_trail` — perform action; assert immutable ClickHouse record + S3 evidence; tamper attempt rejected.
- `test_e2e10_auth_lifecycle` — login, use token, expire, refresh, logout, assert revoked token rejected.

## 13. Cloud / Kubernetes Topology Tests

**Goal:** validate production topology (k8s + Istio + Kong + HPA) on an ephemeral cluster (kind/k3d in CI, or real EKS/GKE/AKS in staging).

**Files to create**
- `tests/cloud/conftest.py` — spin up kind cluster, `kubectl apply -k k8s/` (or Helm), wait for rollouts.
- `tests/cloud/test_k8s_topology.py` — marker `@pytest.mark.k8s`.
- `tests/cloud/test_istio_mesh.py`, `tests/cloud/test_kong_gateway.py`, `tests/cloud/test_hpa.py`.

**Cases**
- All Deployments/StatefulSets reach `Available`; probes (liveness/readiness/startup) defined and passing.
- Istio mTLS `STRICT`: plaintext call between pods is rejected; mTLS call succeeds; fault-injection (delay/abort) VirtualService honored.
- Kong routes + rate-limit plugin + auth plugin enforce as configured; unauthorized route returns 401/403.
- HPA scales Deployment up under synthetic CPU/RPS load and back down; PodDisruptionBudget respected during node drain.
- Node/pod failover: `kubectl delete pod` → traffic continues, no 5xx beyond retry budget.
- Secrets sourced from Vault (CSI/agent), not k8s plaintext Secrets; image pull uses non-root, read-only rootfs where set.

## 14. Security / DAST / Injection Suite

**Goal:** automated coverage of §6.3.

**Files to create**
- `tests/security/test_authz.py` — RBAC matrix, API-key scope enforcement, tenant boundary, JWT tampering (alg=none, expired, wrong-sig → all rejected).
- `tests/security/test_injection.py` — SQL/Cypher injection payload corpus against every parameterized query path; assert no injection succeeds.
- `tests/security/test_prompt_injection.py` — adversarial prompts against each agent; assert guardrails block unsafe tool calls and no data exfiltration in output.
- `tests/security/test_ssrf.py` — connector URL/host validation; internal/metadata endpoints (169.254.169.254, localhost) blocked.
- `tests/security/test_rate_limit_abuse.py` — burst beyond limit → 429 + Retry-After; distributed consistency across replicas.
- `tests/security/test_secrets_hygiene.py` — invoke secret scanner over repo + built images; assert zero findings; assert no secrets in logs.

**Tooling wiring**
- `bandit -r backend intelligence_engine` and `trivy image` gates in `security.yml`.
- OWASP ZAP baseline/full scan job against the staging URL producing a report artifact; fail on High/Critical.
- Dependency audit (`pip-audit` / `npm audit --audit-level=high`).

## 15. Performance / Load / Soak Suite

**Goal:** validate §6.1 SLOs with reproducible scripts and CI thresholds.

**Files to create**
- `perf/k6_api_baseline.js` — ramp to nominal RPS; thresholds `http_req_duration p(95)<300` and `http_req_failed<0.01`.
- `perf/k6_api_soak.js` — sustained load ~1h; assert no memory growth / error creep.
- `perf/kafka_throughput.py` — produce/consume benchmark; assert sustained ≥ target msg/s and consumer lag bounded.
- `perf/agent_latency.py` — measure triage/response agent decision latency P50/P95 against SLO.
- `perf/README.md` — how to run locally and interpret `load_test_results.txt`.

**CI wiring**
- Release-stage job runs k6 baseline against staging; thresholds are pass/fail gates.
- HPA scale test (cross-ref §13) captures scale-up latency and steady-state P95 under load.

## 16. Chaos & Disaster Recovery

### 16.1 Chaos Engineering
**Files to create**
- `tests/chaos/conftest.py` — helpers to kill/pause containers (`docker kill/pause`) or pods (`kubectl delete pod`, chaos-mesh experiments in Cloud).
- `tests/chaos/test_container_kill.py` — marker `@pytest.mark.chaos`.
- `tests/chaos/test_dependency_outage.py`, `tests/chaos/test_network_partition.py`.

**Cases**
- Kill each of the 17 services in turn → assert auto-restart, no data loss, in-flight work re-processed or DLQ'd, DLQ intact.
- Dependency outage matrix (Vault / Redis / Neo4j / Kafka broker / ClickHouse / S3 down): assert fail-closed or graceful degradation per service contract; assert recovery on restore.
- Network partition (Istio abort/delay or `tc` netem): assert retries/timeouts/circuit-breakers behave; no cascading failure.
- Connection storm on WebSocket gateway → assert backpressure, no crash, heartbeat/reconnect works.

### 16.2 Disaster Recovery
**Files to create**
- `tests/dr/test_backup_restore.py` — marker `@pytest.mark.dr`, one case per datastore (Neo4j, ClickHouse, Redis, S3/MinIO, native storage).
- `tests/dr/test_migration_rollback.py` — forward + rollback Alembic migration against production-like volume; assert referential integrity.
- `tests/dr/test_rpo_rto.py` — simulate failure at time T, restore, measure elapsed (RTO) and lost window (RPO); assert within `rollback_plan.md` targets.

**Cases**
- Backup each store → destroy → restore → assert full data parity and app healthy.
- Cross-store consistency after restore (no dangling references between Neo4j/ClickHouse/S3).
- Staged-deploy rollback drill (also gated in CI, §18): deploy known-bad image → health check fails → automatic rollback to previous → smoke passes.

---

# PART III — Workflow Changes to Apply Manually

> These `.github/workflows/*` edits could **not** be committed by the automation (missing "Workflows: Read and write" permission). Apply them via the GitHub web editor, or grant the permission and re-run. After applying, mark §0.2 items ✅.

## 17. `.github/workflows/test.yml` — Cross-platform matrix

Replace the single-OS test job with a matrix. Illustrative shape (merge with the existing job body — keep the existing checkout/setup/deps/test steps):

```yaml
jobs:
  test:
    name: tests (${{ matrix.os }} / py${{ matrix.python }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ['3.11']
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - name: Install deps
        run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Unit + API tests
        run: python -m pytest tests/unit tests/api -v --cov=backend/app --cov=intelligence_engine --cov-report=xml
      # Docker-dependent suites only where a Linux Docker daemon is available:
      - name: Integration (Docker) tests
        if: runner.os == 'Linux'
        run: python -m pytest tests/integration -v -m docker
```

Notes:
- Keep coverage gate (≥85%) on the Linux leg to avoid triple-counting.
- Use `shell: bash` on steps that run shell scripts so they work identically on Windows runners.
- Gate Docker/k8s/chaos suites behind `runner.os == 'Linux'` (Windows/macOS hosted runners lack a usable Docker daemon).

## 18. `.github/workflows/deploy.yml` — Staging chaos/DR rollback release gate

Add a gate that runs **before** promoting to production: deploy to staging, run chaos + DR + rollback drill, only promote if green.

```yaml
jobs:
  staging-resilience-gate:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to staging
        run: ./deploy.sh staging
      - name: Wait for health
        run: ./scripts/wait_for_health.sh staging
      - name: Chaos suite
        run: python -m pytest tests/chaos -v -m chaos
      - name: DR drill (backup/restore + RPO/RTO)
        run: python -m pytest tests/dr -v -m dr
      - name: Rollback drill (deploy bad image -> auto-rollback)
        run: ./scripts/rollback_drill.sh staging

  promote-production:
    needs: staging-resilience-gate
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - name: Staged deploy + canary
        run: ./deploy.sh production --canary
      - name: Canary smoke
        run: python -m pytest tests/integration/test_docker_e2e.py -v -m smoke
      - name: Auto-rollback on failure
        if: failure()
        run: ./deploy.sh production --rollback
```

Notes:
- `promote-production` depends on `staging-resilience-gate`, so a failed chaos/DR/rollback drill blocks release.
- Reuse `rollback_plan.md` procedures inside `scripts/rollback_drill.sh`; if that script doesn't exist yet, create it alongside this change.
- Ensure `deploy.sh` supports `--canary` and `--rollback` flags (referenced by the staged-deploy work already on `main`).
