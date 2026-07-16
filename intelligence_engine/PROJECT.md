# Project: FastAPI Production API Migration

## Architecture
Migrating the monolithic Node.js backend routes from `server.js` to a modular Python FastAPI backend inside `intelligence_engine`. The FastAPI app will use `APIRouter` to structure modular routes, load environment configurations, establish database connections with PostgreSQL, Neo4j, Qdrant, ClickHouse, and Redis, and expose endpoints to the frontend.

### Component Layout
- `intelligence_engine/api/`: Root of the FastAPI modules
  - `api/main.py`: Entry point for modular API (combining or replacing current `main.py`)
  - `api/routes/`: Router modules (health, copilot, investigations, alerts, connectors, playbooks, reports, dashboard)
  - `api/middleware/`: Middleware stack (logging, trace_id, error handling)
- `intelligence_engine/core/`: Existing core business logic, connectors, database accessors, and graph reasoning engines.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Research & Mapping | Deep code audit of Node.js routes in `server.js`, database dependencies, and mapping to FastAPI endpoints. | None | DONE |
| 2 | Router Framework & Core Models | Set up `api/routes/` routing directory, common models, database integration helpers, and baseline `main.py`. | M1 | DONE |
| 3 | health & dashboard Routers | Implement health check & dashboard stats endpoints (integrating PostgreSQL and ClickHouse checks). | M2 | DONE |
| 4 | alerts & investigations Routers | Implement alert listing/details, investigation details/trigger/explain endpoints. | M2 | DONE |
| 5 | copilot, playbooks & reports Routers | Implement chat assistant queries, SOAR playbook execution, report digests and audit logs. | M2 | DONE |
| 6 | connectors & storage Routers | Implement EDR/SIEM connector status/sync, and storage upload routes. | M2 | DONE |
| 7 | Middleware Stack & Logger | Implement request trace_id injection, global exception handlers, and structured logging middleware. | M3-M6 | DONE |
| 8 | E2E Testing & Validation | Develop full `pytest` suite using `TestClient`, run audits, and verify trace_ids in logs. | M7 | DONE |

## Interface Contracts
### Node.js API Gateway ↔ FastAPI Production API
- All migrated endpoints prefix: `/api/v1/`
- Request/response format: JSON (utf-8)
- Middleware: CORS support, application/json validation, error mapping
