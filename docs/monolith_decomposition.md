# Monolith Decomposition Plan (`server.js`)

The `server.js` file is currently 2,029 lines and serves as a monolithic Node.js backend. This plan details how to systematically decompose it into a scalable hybrid architecture.

## 1. Routes to KEEP in Node.js
These routes rely heavily on Node's strengths (I/O, WebSocket handling, UI serving) and should remain in `server.js` or be factored out into Node.js microservices eventually:
- `GET /` and all static asset serving (React build)
- WebSocket server (`io.on('connection')`) for real-time alerts
- Auth layer (until migrated to a dedicated auth service)

## 2. Routes to PROXY to Python (Intelligence Engine)
These endpoints trigger AI, ML, or complex data reasoning. They must be forwarded to FastAPI (`http://intelligence-engine:8001`):
- `POST /api/v1/copilot/query` (Already proxied)
- `POST /api/v1/investigate` (Already proxied)
- `POST /api/v1/investigation/explain` (Already proxied)
- **Upcoming:** `/api/v1/alerts/{id}/investigate`
- **Upcoming:** `/api/v1/playbooks/{id}/execute`

## 3. Routes to MIGRATE (Phase 5+)
These are currently in `server.js` using mock data, but need to be rebuilt in FastAPI with real database persistence:
- `/api/v1/alerts` (Move to Python PG queries)
- `/api/v1/investigations` (Move to Python PG queries)
- `/api/v1/reports` (Move to Python reporting engine)
- `/api/v1/dashboard/stats` (Move to Python / ClickHouse queries)

## Execution Strategy
1. **Strangler Fig Pattern:** Add new features only to the Python Intelligence Engine.
2. **Incremental Proxying:** As a route is built in Python, add it to the Node.js proxy list.
3. **Deprecation:** Once proxied, remove the old mock logic from `server.js`.
4. **Final State:** Node.js becomes purely an API Gateway and WebSocket proxy.
