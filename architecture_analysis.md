# 🛡️ EDYSOR - System Architecture Analysis

This document provides a comprehensive architectural analysis of the **EDYSOR (Enterprise Defense & Yield Security Operations Responder)** platform as of **Milestone 1**. It validates the existing services, local runtimes, database layers, environment requirements, and readiness for cloud migration.

---

## 1. Core Architecture Overview
EDYSOR is built as a highly scalable, multi-tier, AI-native Security Operations Center (SOC) designed to process high-throughput security telemetry, cluster threats, evaluate incidents using a Gemini Multi-Agent Swarm, and perform simulated containment exercises.

The system is split into two major software packages and a series of supportive infrastructure services:
1. **Frontend Applet (`/frontend`)**: A modern SPA built on Next.js (V16), React (V19), and Tailwind CSS (V4). It uses Zustand for local state management, Recharts for analytics, and Cytoscape for visual network topology rendering.
2. **Backend Engine (`/server.js`)**: An Express-based full-stack Node.js application that handles REST API routes, WebSocket streaming (for live alert ingestion), and third-party API integrations (Gemini API, Neo4j Graph Driver, Qdrant Client).
3. **Infrastructure Services (Docker Compose Setup)**:
   - **Kafka (KRaft Broker)**: Telemetry pipeline stream.
   - **ClickHouse**: OLAP columnar store for time-series events.
   - **PostgreSQL**: Production relational state engine (as specified in `docker-compose.yml`).
   - **Redis**: High-speed rate limiting and WAF active defense caching.
   - **Qdrant**: Vector database providing semantic search and memory storage for threat signatures.
   - **Neo4j**: Graph database modeling network asset topology and "Digital Twin" blast-radii.
   - **Monitoring/Telemetry Stack**: Prometheus, Grafana, and Jaeger (OpenTelemetry tracing).
   - **Canaries/Honeypots**: Cowrie (SSH/Telnet honeypot) and Dionaea (Multi-protocol honeypot).
   - **Containment Orchestration**: Caldera (Mitre CND framework agent).

---

## 2. Database & State Analysis

### Local vs. Production Relational State
* **Local Workspace State (`/server.js`)**:
  - The currently executing Node.js server utilizes a local **SQLite3 file database** (`shieldai.db`) for handling persistent user tables (such as authentication accounts and roles).
  - Incidents, alerts, and system playbooks are temporarily handled as in-memory data structures (arrays) inside `server.js` for lightweight simulation during rapid local development.
* **Production/Docker Configuration (`docker-compose.yml`)**:
  - Docker Compose specifies a containerized **PostgreSQL (v16)** database (`shieldai-postgres`) as the enterprise-grade store.
  - The docker-compose backend environments are pre-wired with configuration parameters like `DB_TYPE=postgres` and connection URLs (`POSTGRES_URL`), indicating that the platform intends to swap to PostgreSQL in production environments.

---

## 3. Core Component Mapping & Technologies

| Service Category | Component Name | Technology Stack | Connection Protocol / Port | Role in Architecture |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend UI** | `soc-frontend` | Next.js 16 / React 19 / Cytoscape / Tailwind CSS | HTTP / Port `80` (External) | Serves the interactive analyst portal, threat graphs, and AI console. |
| **Backend API** | `soc-backend` | Node.js Express / WebSockets (`ws`) | HTTP & WS / Port `3000` (Local) / `8000` (Docker) | Powers core APIs, streams live alerts, orchestrates AI agents, and manages DB client pools. |
| **State Database** | `postgres` | PostgreSQL 16 (Alpine-based image) | TCP / Port `5432` | Stores robust relational user authentication, tenancy definitions, and RBAC policies. |
| **Transient Cache**| `redis` | Redis 7 (Alpine-based image) | TCP / Port `6379` | Fast memory store used by WAF modules to enforce rate limits and store blocks. |
| **Vector DB** | `qdrant` | Qdrant Vector Engine | HTTP / Port `6333` / `6334` | Houses incident embedding vectors using `text-embedding-04` for AI memory lookup. |
| **Graph DB** | `neo4j` | Neo4j Community Edition | HTTP/Bolt / Ports `7474`, `7687` | Builds active security asset topologies to calculate attack path blast radiuses. |
| **Stream Bus** | `kafka` | Apache Kafka (Confluent CP 7.5.0) | TCP / Port `9092` (Local) / `29092` (Docker) | Processes real-time logs and signals for high-throughput security event stream analysis. |
| **Data Warehouse**| `clickhouse` | ClickHouse Columnar Database | HTTP/TCP / Ports `8123`, `9000` | High-speed ingestion store for logs, metrics, and security telemetry events. |
| **APM / Tracing** | `jaeger` | Jaeger All-in-One | OTLP / Ports `16686` (UI), `4317` (gRPC) | Gathers end-to-end trace context metrics from API handlers to audit pipeline performance. |

---

## 4. Environment Variables Validation
Based on the system analysis, the following environment variables dictate integration patterns across services:

1. **AI Engines**:
   - `GEMINI_API_KEY`: API key used to initialize `@google/genai` to drive autonomous triages.
2. **Relational Database**:
   - `DB_TYPE`: Determines which driver code path to spin up (`sqlite` vs `postgres`).
   - `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD`: Specific connection details.
   - `POSTGRES_URL`: Fully constructed PostgreSQL connection string.
3. **Graph Topology**:
   - `NEO4J_URI`: Connection endpoint (e.g. `bolt://localhost:7687`).
   - `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE`: Credentials and active database name.
4. **Vector Memory**:
   - `QDRANT_URL`: Endpoint representing the Qdrant server.
   - `QDRANT_API_KEY`: Token to authorize rest requests.
5. **App Security**:
   - `JWT_SECRET`: Secret used to sign JSON Web Tokens.

---

## 5. Summary of Architecture Validation Findings
1. **Business Logic Integrity**: No business logic modification is required. The endpoints and route paths in `server.js` map to modular actions (fetching alerts, recording incidents, creating nodes) that are database-engine independent.
2. **Database Migration Drivers**: Swapping the relational state from local SQLite to Google Cloud SQL (PostgreSQL) requires adding the PostgreSQL Node driver (`pg`) to `package.json` and introducing a unified database connector module supporting environment-driven selection.
3. **Graceful Fallbacks**: The server exhibits highly robust engineering characteristics, utilizing safe try-catch blocks and checks around `NEO4J_URI`, `QDRANT_URL`, and `GEMINI_API_KEY` to gracefully fall back or mock operations when specialized infrastructure is missing. This prevents the server from crashing on startup if secondary databases are initialized asynchronously.
