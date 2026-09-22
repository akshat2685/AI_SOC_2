# ShieldAI (EDYSOR) — Autonomous AI SOC Platform

> **Project status: early-stage scaffold — not production ready.**
> This README describes what the code *actually does* as of 2026-09-22 (rewritten after a full line-by-line audit of all 353 files). Anything aspirational is labeled as such. The backend **does not boot** as committed — see [Known blockers](#known-blockers).

## What this is

An early-stage **FastAPI + Next.js** security-operations dashboard scaffold:

- Multi-tenant Postgres data model (tenants, users, assets, alerts, incidents, API keys, audit events, compliance)
- JWT + API-key authentication with RBAC and rate limiting
- Alert / incident / notification / compliance REST APIs backed by Postgres
- A Next.js dashboard UI that fetches from `/api/v1`

**Not yet implemented:** the agent swarm, threat-intel ingestion, SOAR playbook execution, honeypot integration, and multi-datastore analytics. Schema DDL for some of these exists; working code does not.

## What works today

| Area | Reality |
|---|---|
| Auth | `POST /login` (bcrypt + JWT), `POST /register`, full API-key lifecycle (create / list / rotate / revoke) with SHA256-hashed storage and scopes |
| Middleware | Request tracing, dual auth (JWT bearer + `X-API-Key`), audit logging of mutating requests, per-route rate limiting (slowapi) |
| Alerts | Real DB-backed list/get/create; responses overlay hardcoded demo fields (severity `MEDIUM`, confidence `80%`) |
| Incidents | Real DB-backed list/get; verdict/risk/graph endpoints return hardcoded values (no ML model exists) |
| Notifications | Preference CRUD + webhook endpoints with HMAC-signed test delivery |
| Compliance | Posture-score computation from DB tables |
| Frontend | Next.js app; Dashboard, Incidents, Attack Graph, Executive views genuinely call `/api/v1` (several other views render mock data) |
| DB setup | Alembic migrations, `init_db.py` / `seed_db.py` standalone scripts |
| Infra | `docker-compose.yml` composes 16 services (Postgres, Redis, Kafka, ClickHouse, Neo4j, Qdrant, Jaeger, Prometheus, Grafana, Vault, Cowrie, Dionaea, frontend, backend, worker, ai-layer) — **containers only; most are not wired to the app** |

## What is stubbed, fake, or decorative

- **22 stub routes** mounted with **no authentication** (`api/v1/stub_routes.py`): `/chat` returns a fixed string ("I am the AI Copilot…"), `/mitre/mappings` → `[]`, `/threat-intel/*` → `{"intel": "No data"}`, `/firewall/*` and `/threat-intel/sync` → fake `{"status": "success"}` doing nothing, `/payments/*` → fake billing
- **Kafka / ClickHouse**: producer/consumer/audit-consumer code exists but is never instantiated; `aiokafka` / `clickhouse_connect` aren't even in `requirements.txt`
- **Neo4j / Qdrant**: drivers are constructed at import; **zero queries** are executed anywhere
- **Redis**: no client code; only a slowapi `storage_uri` default
- **Honeypots**: Cowrie + Dionaea run as containers; no code reads their data
- **`ai/` package** (`confidence_scoring.py`, `explainability.py`, `output_validation.py`): real, decent utility code — **imported by nothing**
- **Agent prompts** (`TRIAGE_ANALYST_PROMPT.md`, `SUPERVISOR_PROMPT.md`, etc.): orphaned, loaded by no code
- **Parallel auth/RBAC/session modules** (`app/auth/`): complete but unused; the live path is `core/security.py` + `api/deps.py`
- **Tests**: 3 files, 6 tests; none cover agents, incidents, Kafka, or Neo4j
- **CI workflows** reference requirements files, test paths, and Dockerfiles that don't exist — they cannot pass

## True architecture (as coded)

```
Next.js frontend (:80) ──HTTP──▶ FastAPI backend (:8000)
                                        │
                        ┌───────────────┼────────────────┐
                        ▼               ▼                ▼
                 Postgres :5432   stub_routes      SQLAlchemy repos
                 (only wired      (22 fake routes,  (real code, zero
                  datastore)      no auth)          callers — routes
                                                    hand-roll SQL)
```

Infra services present in compose but **not consumed by the app**: Kafka, ClickHouse, Neo4j, Qdrant, Redis, Jaeger, Prometheus, Grafana, Vault, Cowrie, Dionaea. `siem-worker` and `ai-layer` cannot build (they `COPY intelligence_engine/`, which doesn't exist). Prometheus/Grafana/Vault configs referenced in compose are absent.

## Repository map

```
backend/app/
  main.py                 FastAPI wiring (routers + middleware). Does not boot — see below
  api/v1/                 alerts, incidents, auth, api_keys, notifications, compliance, stub_routes
  ai/                     confidence_scoring / explainability / output_validation (real, unwired)
  application/            alert processing service + audit logger (Kafka hop dead: no aiokafka)
  auth/                   oauth2 / rbac / session_manager (complete, unused, contains hardcoded secret)
  core/                   config (7 required env vars), security (bcrypt+jose), logger, auth contextvars
  domain/                 19 SQLAlchemy models + Pydantic schemas (the solid part)
  infrastructure/         storage engine (Postgres real; Neo4j/Qdrant ornamental), event bus (stub only),
                          repositories (real, unused), audit_consumer (complete pipeline, never started)
  workers.py              demo loop on in-memory stub bus (broken imports)
frontend/                 Next.js (not React+Vite). Real views: Dashboard, Incidents, Attack Graph, Executive.
                          Mock-data views: Chaos, Federation, AR threat map, SaaS payment wall, voice bar
*_PROMPT.md               7 agent prompt files, loaded by nothing
docker-compose.yml        16 services; 2 unbuildable, most unwired
```

## Running it

**Prereqs:** Docker, and two code fixes (backend won't start without them).

1. **Fix the fatal imports** — remove/replace:
   - `backend/app/api/v1/alerts.py:12` (`from intelligence_engine.agents.soc_orchestrator import run_orchestrator`)
   - `backend/app/api/v1/notifications.py:23-26` (`intelligence_engine.core.crypto` → nonexistent fallback)
2. **Set the 7 required env vars** (`backend/app/core/config.py` raises `ValueError` without them): `GEMINI_API_KEY`, `SOAR_API_KEY`, `SOAR_API_ENDPOINT`, `POSTGRES_URL`, `SECRET_KEY`, `KAFKA_BOOTSTRAP_SERVERS`, `AUDIT_SECRET_KEY` — or copy `.env.example` and fill it in
3. `docker compose up -d` (Postgres is the only datastore the app actually needs)
4. API at `http://localhost:8000/docs` · frontend at `http://localhost` (port 80)

Honest expectation after the fixes: auth + API keys + alerts/incidents CRUD against Postgres, plus a dashboard UI — with a set of fake stub endpoints alongside the real ones.

## Known blockers

1. **Backend doesn't boot** (phantom `intelligence_engine` imports + 7-var env gate)
2. **No AI**: no LLM SDK, no agent code, prompts orphaned — "multi-agent swarm" exists only in docs
3. **No threat-intel pipeline**: no STIX/TAXII/feeds/OTX/VirusTotal anywhere
4. **No SOAR execution**: only DDL tables (`playbooks` defined twice, incompatibly)
5. **Auth gaps**: only 3 routers enforce auth; alerts/incidents/stubs silently serve tenant 1 to anonymous requests

## ⚠️ Security warnings — do not expose this publicly

- `backend/app/auth/oauth2.py` contains a **hardcoded production secret** (unused module, but committed)
- `POST /register` grants **TENANT_ADMIN to anyone**, no verification
- `SaaSPaymentWall.tsx` POSTs **raw card number/expiry/CVC** to the backend with no payment processor
- `fix-db.mjs` injects `admin`/`password` credentials
- 22 unauthenticated stub routes are mounted in `main.py`

## Honest roadmap

1. Make the backend boot (fix phantom imports, relax env gate for dev)
2. Delete or gate the 22 stub routes; fix `/register` and remove committed secrets
3. Build **one** real pipeline end-to-end: ingest → score → alert → case (this is the missing organ)
4. Wire the orphaned `ai/` utilities into that pipeline
5. Add threat-intel ingestion (STIX/TAXII or OTX free API) before adding more datastores
6. Only then: agents, SOAR runner, honeypot consumers — one at a time, each wired, none decorative

## Docs vs. reality

Several docs describe a different or future system: `architecture_analysis.md` describes an Express `server.js` backend (doesn't exist), `deployment_report.md` claims a signed-off production deployment (the deploy script has unfilled placeholders), and `PRODUCT_DOCUMENTATION.md` documents features with no code behind them. Treat all docs except this README as aspirational until verified against code.
