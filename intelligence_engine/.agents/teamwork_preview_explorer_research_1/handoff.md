# Handoff Report - teamwork_preview_explorer_research_1

## 1. Observation
The following observations were made after examining `PROJECT.md`, `server.js`, and the Python files within `intelligence_engine`:

### Route 1: `/health`
- **Monolith Node.js Implementation**:
  - File: `server.js` (lines 569-571)
  - Method: `GET`
  - Exact path: `/health`
  - Parameters: None
  - Response structure: Plaint-text string `"OK"` with Status 200.
  - DB hooks: None.
- **Proposed Python/FastAPI Implementation**:
  - File: `intelligence_engine/main.py` (lines 21-23)
  - Method: `GET`
  - Path: `/health`
  - Parameters: None
  - Response structure: JSON `{"status": "healthy", "service": "intelligence-engine"}`
  - DB hooks: None in router.
- **Python Service Mapping**:
  - File: `intelligence_engine/core/health.py` (lines 9-76)
  - Service Class: `HealthChecker`
  - Aggregates health states of PostgreSQL, Neo4j, Qdrant, Kafka, and Redis via `aggregate()` using `asyncio.gather`.
  - Under the hood, these methods are currently mocked with `# TODO: Implement actual connection check` and small sleep latencies.

### Route 2: `/api/v1/copilot/query`
- **Monolith Node.js Implementation**:
  - File: `server.js` (lines 2004-2013)
  - Method: `POST`
  - Path: `/api/v1/copilot/query`
  - Parameters: Proxies whatever body is received directly via helper `proxyToIntelligenceEngine`.
  - Response structure: Forwarded JSON response from Python service.
  - DB hooks: None in Node.js gateway.
- **Proposed Python/FastAPI Implementation**:
  - File: `intelligence_engine/main.py` (lines 47-67)
  - Method: `POST`
  - Path: `/api/v1/copilot/query`
  - Parameters: JSON request body validated by Pydantic model `QueryRequest(BaseModel)` containing field `query: str`.
  - Response structure: JSON response containing fields: `answer` (string), `evidence` (list of strings), `confidence` (float), `sources` (list of strings), `mitre_mapping` (list of strings).
  - DB hooks / Core Logic: Calls LangChain's `ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)` with system and human message prompts requesting strict JSON format output.
- **Python Service Mapping**:
  - File: `intelligence_engine/core/config.py` (lines 15-16, 29-34)
  - Settings: `AISettings` loads `gemini_api_key` from environment.

### Route 3: `/chat`
- **Monolith Node.js Implementation**:
  - File: `server.js` (lines 1882-1997)
  - Method: `POST`
  - Path: `/chat`
  - Parameters: JSON request body `{ query: string }`. Returns 400 error `{ error: 'Missing query parameter in request body' }` if missing.
  - Response structure: JSON response `{ response: string }`.
  - DB hooks:
    1. **Qdrant Vector DB Search**: Calls `searchQdrantMemories(query)` which fetches semantic matches from vector memory collection `shieldai_memories`.
    2. **Neo4j Graph DB Search**: Runs Cypher query to match nodes whose id or ip contains the query (limit 5):
       ```cypher
       MATCH (n) 
       WHERE n.id CONTAINS $query OR (exists(n.ip) AND n.ip CONTAINS $query)
       RETURN n, labels(n)[0] AS label LIMIT 5
       ```
    3. **Gemini API Generation**: Prompts `gemini-3.5-flash` using retrieved vector and graph contexts.
- **Proposed Python/FastAPI Implementation**:
  - Not yet implemented in `main.py` or `main_dashboard_api.py`. Planned for Milestone 5.
- **Python Service Mapping**:
  - **Qdrant Vector DB access**: `intelligence_engine/memory/experience_replay.py` -> class `SOCExperienceReplay` (manages vector database setup and upsert operations for `soc_memory` collection).
  - **Neo4j Graph DB access**: `intelligence_engine/graph/neo4j_reasoning.py` -> class `AttackGraphReasoningEngine` (implements graph queries such as `find_blast_radius`).

### Route 4: `/api/v1/dashboard` (or `/stats`, or `risk-heatmap`)
- **Monolith Node.js Implementation**:
  - **Endpoint 1**: `/stats` (GET, lines 1631-1642):
    - Path: `/stats`
    - Parameters: None
    - Response structure: JSON containing incident, alert, blocked IP counts, event rate, pending approvals, and log counts.
    - DB hooks: Reads from in-memory arrays `incidents`, `alerts`, `firewallBlocks`.
  - **Endpoint 2**: `/api/v1/executive/metrics` (GET, lines 1604-1622):
    - Path: `/api/v1/executive/metrics`
    - Parameters: None
    - Response structure: JSON containing averages for risk score (42.5), MTTD (12.8), MTTR (45.4), precision (94.2), total cost prevented, and weekly trends.
    - DB hooks: Hardcoded mock JSON.
- **Proposed Python/FastAPI Implementation**:
  - File: `intelligence_engine/main_dashboard_api.py` (lines 10-27)
  - **Endpoint 1**: `/api/alerts` (GET) -> returns `{"alerts": alerts}` list.
  - **Endpoint 2**: `/api/alerts` (POST) -> body parameters: custom JSON `alert: dict`.
  - **Endpoint 3**: `/api/risk-heatmap` (GET) -> returns `{"heatmap": [{"region": string, "risk_score": int}]}` with random risk scores.
  - **Endpoint 4**: `/ws/alerts` (WebSocket) -> streams latest alert JSON every 5 seconds.
- **Python Service Mapping**:
  - **ClickHouse Storage**: `intelligence_engine/core/clickhouse_writer.py` -> class `ClickHouseWriter` (stores events to ClickHouse, has `write_batch`, `flush`, and `query` methods).
  - **PostgreSQL incident persistence**: `intelligence_engine/core/memory_learning.py` -> class `MemoryLearningSystem` (contains methods to `record_incident`, `get_incident_memory`, and `get_pending_approvals` from PostgreSQL `incident_memory` and `action_approvals` tables).

---

## 2. Logic Chain
1. By inspecting the Express routes in `server.js` and the FastAPI apps in `main.py` and `main_dashboard_api.py`, we identified the complete paths, HTTP methods, input parameters, and responses for the four route types.
2. In `server.js` (line 2004), `/api/v1/copilot/query` is a simple HTTP proxy to the Python engine. The Python engine implements this route in `main.py` using `langchain_google_genai` to parse user queries.
3. The `/chat` endpoint in `server.js` is a rich hybrid RAG endpoint querying both Qdrant (using embeddings) and Neo4j (using graph queries). Although the Python engine currently lacks a `/chat` API endpoint, the necessary interfaces are already developed as `SOCExperienceReplay` (in `memory/experience_replay.py`) and `AttackGraphReasoningEngine` (in `graph/neo4j_reasoning.py`).
4. Dashboard and Stats endpoints in the Node monolith return aggregate metrics from in-memory arrays. In the Python workspace, `main_dashboard_api.py` exposes mock `/api/risk-heatmap` and `/api/alerts` routes, while `core/clickhouse_writer.py` and `core/memory_learning.py` are the corresponding backend services implementing real database query writers and readers.
5. In `core/health.py`, `HealthChecker` handles Postgres, Neo4j, Qdrant, Kafka, and Redis checks. However, it lacks a ClickHouse health check, which is explicitly requested in `PROJECT.md` Milestone 3.

---

## 3. Caveats
- No physical pytest tests were run because the command-line executor permission prompt timed out.
- There is a mismatch on the `/api/v1/investigate` route: Express forwards the request body to `/api/v1/investigate`, but FastAPI's router expects `alert_id` as a query parameter (`alert_id: str`). This will cause a `422 Unprocessable Entity` validation failure on the proxy.
- The `HealthChecker` class in `core/health.py` contains mock latency delays (`await asyncio.sleep(0.01)`) and needs real socket/session checks.

---

## 4. Conclusion
The HTTP routes, parameters, responses, and DB query hooks have been fully audited, and their corresponding Python service classes successfully mapped. Key design discrepancies (mismatched proxy body-to-query params and missing ClickHouse health checks) have been flagged for the implementation phase.

---

## 5. Verification Method
To verify this analysis:
1. View the routing code in `C:\Users\ijain\AI_SOC_2\intelligence_engine\main.py` (lines 47-89) and `main_dashboard_api.py` (lines 10-38).
2. Check the core class mappings by reviewing:
   - `C:\Users\ijain\AI_SOC_2\intelligence_engine\core\health.py` (lines 9-76) for health checking details.
   - `C:\Users\ijain\AI_SOC_2\intelligence_engine\memory\experience_replay.py` (lines 5-33) for vector database interactions.
   - `C:\Users\ijain\AI_SOC_2\intelligence_engine\graph\neo4j_reasoning.py` (lines 3-22) for graph queries.
   - `C:\Users\ijain\AI_SOC_2\intelligence_engine\core\memory_learning.py` (lines 6-102) for Postgres integration.
3. Validate that pytest is set up correctly by inspecting `C:\Users\ijain\AI_SOC_2\intelligence_engine\tests\test_main_api.py`.
