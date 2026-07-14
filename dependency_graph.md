# 📊 EDYSOR - Dependency Graph

This document details the dependency graph and communication vectors of the **EDYSOR** security platform. It maps out how data flows through the application tiers, how services interact, and the critical path for cloud-native orchestration.

---

## 1. Visual Dependency Graph (ASCII)

```text
                  +-----------------------------------+
                  |        Analyst Browser UI         |
                  |     (React SPA / Cytoscape)       |
                  +-----------------------------------+
                        |                     ^
             HTTP REST  |                     |  WebSockets
             Request    v                     |  Live Signals
                  +-----------------------------------+
                  |         Express Backend           | <---+ [ Rate-Limiting ]
                  |          (server.js)              |     | (Redis Cache)
                  +-----------------------------------+
                     |           |             |
     +---------------+           |             +-----------------+
     | SQL Queries               | Bolt Auth                     | HTTP Requests
     v                           v                               v
+-----------+              +-----------+                   +-----------+
| State DB  |              | Graph DB  |                   | Vector DB |
| Postgres  |              |   Neo4j   |                   |  Qdrant   |
+-----------+              +-----------+                   +-----------+
                                                                 ^
                                                                 | Generates
                                                                 | Embeddings
                                                                 |
                                                           +-----------+
                                                           | Google AI |
                                                           |  Gemini   |
                                                           +-----------+
```

---

## 2. Dynamic Pipeline & Telemetry Data Flow

In addition to state-driven REST operations, the telemetry engine processes asynchronous events. This pipeline is laid out below:

```text
                  +-----------------------------------+
                  |      External Honeypots / Canaries|
                  |        (Cowrie, Dionaea)          |
                  +-----------------------------------+
                                    |
                                    | Raw Telemetry Syslogs
                                    v
                  +-----------------------------------+
                  |      Stateless Ingestion API      |
                  +-----------------------------------+
                                    |
                                    | Kafka Produce
                                    v
                  +-----------------------------------+
                  |         Kafka KRaft Bus           |
                  +-----------------------------------+
                       |                             |
                       | Batch Write                 | Stream Consume
                       v                             v
            +--------------------+        +--------------------+
            | Columnar Analytics |        | AI Swarm Detection |
            |    (ClickHouse)    |        | (IsolationForest)  |
            +--------------------+        +--------------------+
                                                     |
                                                     | Triggers Verdict
                                                     v
                                          +--------------------+
                                          | Express REST API   |
                                          |  (State Update)    |
                                          +--------------------+
```

---

## 3. Dependency Descriptions & Connection Matrix

The table below catalogs connection details, protocol types, and dependency modes for the backend engine:

| Source Service | Target Service | Connection Type | Library Used | Dependency Criticality | Fallback Mechanism |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `soc-frontend` | `soc-backend` | REST (JSON) & WebSockets | Native Fetch / WebSocket | **CRITICAL** | User experiences offline-mode banner; retries connection. |
| `soc-backend` | `postgres` | SQL Queries (TCP/5432) | `pg` (Postgres Client) | **CRITICAL** | Falls back to local SQLite (`shieldai.db`) for lightweight sandbox environments. |
| `soc-backend` | `redis` | TCP Cache (TCP/6379) | `redis` | **MEDIUM** | Standard in-memory maps inside Node process bypass active rate blocks. |
| `soc-backend` | `neo4j` | Bolt Binary (TCP/7687) | `neo4j-driver` | **LOW** | Bypasses actual graph rendering and serves static mock asset relationships. |
| `soc-backend` | `qdrant` | HTTP REST (TCP/6333) | `@qdrant/js-client-rest` | **LOW** | Stores historical search memories in a local fallback JSON array. |
| `soc-backend` | `Gemini API` | HTTPS API (External) | `@google/genai` | **HIGH** | Uses deterministic, heuristic analyst rulesets to flag alerts. |

---

## 4. Key Takeaways for Cloud Migration
* **No Stateful Barriers**: The API server is inherently stateless; all critical configurations, user data, and active records reside in external databases (PostgreSQL, Qdrant, Neo4j). This allows the frontend and backend instances to be deployed in scalable containers (e.g., Google Cloud Run or GKE) behind standard load balancers.
* **Separation of Database Runtimes**: Relational, vector, and graph databases have completely independent connection drivers. Migrating SQLite to Cloud SQL will not affect graph (Neo4j) or vector (Qdrant) connection channels, which remain fully operational via their independent URI strings.
