# Research & Mapping Handoff Report

## 1. Observation
We conducted a comprehensive audit of routes and service mappings within `server.js` and the `intelligence_engine/` directory.

### Monolithic API Endpoints in `server.js`
The following endpoints were verified by reading `C:\Users\ijain\AI_SOC_2\server.js`:

#### A. Alerts Routes
*   **`GET /api/v1/alerts`** (Line 1407)
    *   **Parameters**: None.
    *   **Response Structure**: JSON Array of Alert objects.
        ```json
        [
          {
            "id": 101,
            "timestamp": "2026-07-15T14:06:31.000Z",
            "title": "Unauthorized SSH Key Addition",
            "severity": "CRITICAL",
            "confidence": "94%",
            "confidence_score": 94,
            "attack_type": "CREDENTIAL_ACCESS",
            "evidence": "Modified /root/.ssh/authorized_keys by unprivileged process UID: 1001",
            "attacker_ip": "198.51.100.42",
            "verdict": "TRUE_POSITIVE",
            "incident_id": 1,
            "tenant_id": "default"
          }
        ]
        ```
    *   **Database Query**: Purely in-memory read from the `alerts` array.

*   **`GET /alerts/:id/details`** (Line 1411)
    *   **Parameters**: `id` (Path, integer).
    *   **Response Structure**: Single Alert object (same fields as above). Returns `404` status with `{ "error": "Alert not found" }` if not found.
    *   **Database Query**: In-memory filter on `alerts` by parsed `id`.

*   **`GET /alerts/:id/investigation`** (Line 1418)
    *   **Parameters**: `id` (Path, integer).
    *   **Response Structure**:
        ```json
        {
          "alert_id": 101,
          "investigation_steps": [
            { "step": 1, "action": "Query reputation of source IP 198.51.100.42", "status": "FINISHED", "result": "..." }
          ],
          "ai_conclusion": "Strong indicator of automated command injection..."
        }
        ```
    *   **Database Query**: None (mock JSON returned).

*   **`POST /alerts/:id/investigate`** (Line 1431)
    *   **Parameters**: `id` (Path, integer).
    *   **Response Structure**:
        ```json
        {
          "status": "triggered",
          "alert_id": 101,
          "message": "ShieldAI Investigation Orchestrator started asynchronous Deep Analysis."
        }
        ```
    *   **Database Query**: None (mock JSON returned).

*   **`GET /alerts/:alertId/report.pdf`** (Line 1774)
    *   **Parameters**: `alertId` (Path, string).
    *   **Response Structure**: PDF Binary. Sets headers `Content-Type: application/pdf` and `Content-Disposition: attachment; filename=edysor_alert_<alertId>.pdf`.
    *   **Storage Query**: Uploads PDF buffer to Google Cloud Storage (GCS) under path `reports/edysor_alert_<alertId>.pdf` using `uploadToGCS`.

#### B. Incidents / Investigations Routes
*   **`GET /api/v1/incidents`** (Line 926)
    *   **Parameters**: None.
    *   **Response Structure**: JSON Array of Incident objects.
        ```json
        [
          {
            "id": 1,
            "timestamp": "2026-07-15T12:06:31.000Z",
            "title": "Kubernetes API Server Bruteforce",
            "severity": "CRITICAL",
            "status": "OPEN",
            "correlation_key": "corr-k8s-brute-001",
            "llm_summary": "Multiple failed authentication requests...",
            "verdict": "SUSPICIOUS",
            "analyst_notes": "Checking source IPs...",
            "resolved_at": null,
            "tenant_id": "default"
          }
        ]
        ```
    *   **Database Query**: In-memory read from `incidents` array.

*   **`GET /incidents/:id/details`** (Line 930)
    *   **Parameters**: `id` (Path, integer).
    *   **Response Structure**: Incident object extended with nested lists for `logs`, `alerts`, `related_logs`, `iocs`, and `actions`. Returns `404` status with `{ "error": "Incident not found" }` if not found.
    *   **Database Query**: In-memory filter on `incidents`, `alerts`, and `auditLogs`.

*   **`GET /api/v1/incidents/:id/predict-risk`** (Line 956)
    *   **Parameters**: `id` (Path, integer).
    *   **Response Structure**:
        ```json
        {
          "incidentId": 1,
          "riskScore": 85,
          "riskLevel": "Critical",
          "likelihood": "85%",
          "reasoning": "...",
          "mitigation": "...",
          "timestamp": "2026-07-15T14:06:31.000Z"
        }
        ```
    *   **LLM Integration**: Invokes Gemini API model `gemini-3.5-flash` to generate fields. Falls back to deterministic rules if `ai` is null.
    *   **Database Query**: None.

*   **`GET /api/v1/incidents/:id/recommended-triage`** (Line 1073)
    *   **Parameters**: `id` (Path, integer).
    *   **Response Structure**: Contains similar historical incidents, threat intelligence profiles, and matching playbooks.
    *   **LLM Integration**: Invokes Gemini API model `gemini-3.5-flash`. Falls back to keyword matching if `ai` is null.
    *   **Database Query**: None.

*   **`PUT /api/v1/incidents/:id`** (Line 1353)
    *   **Parameters**: `id` (Path, integer). Body: Optional `{ status, verdict, analyst_notes }`.
    *   **Response Structure**: Updated Incident object. Returns `404` status with `{ "error": "Incident not found" }` if not found.
    *   **Database Query**: In-memory update. Appends action to in-memory `auditLogs`.

*   **`POST /incidents/:id/verdict`** (Line 1378)
    *   **Parameters**: `id` (Path, integer). Body: `{ verdict, notes }`.
    *   **Response Structure**: `{ "status": "success", "incident": <updated incident> }`. Returns `404` if not found.
    *   **Database Query**: In-memory update. Appends action to in-memory `auditLogs`.

*   **`GET /api/v1/incidents/:id/graph`** (Line 1398)
    *   **Parameters**: `id` (Path, integer).
    *   **Response Structure**: `{ nodes: [...], edges: [...] }` compatible with Cytoscape.
    *   **Database Query**: None (returns the global topology mock).

*   **`POST /api/v1/investigate`** (Line 2016)
    *   **Parameters**: Body (json).
    *   **Response Structure**: Forwards Python backend's accepted JSON.
    *   **Database Query**: None. Proxies to `/api/v1/investigate` on the Python FastAPI service.

*   **`POST /api/v1/investigation/explain`** (Line 2028)
    *   **Parameters**: Body (json).
    *   **Response Structure**: Forwards Python explanation payload.
    *   **Database Query**: None. Proxies to `/api/v1/investigation/explain` on the Python FastAPI service.

#### C. Reports Routes
*   **`GET /api/v1/reports/digest`** (Line 1789)
    *   **Parameters**: `period` (Query, string, optional, default: `"week"`).
    *   **Response Structure**: PDF Binary. Sets headers `Content-Type: application/pdf` and `Content-Disposition: attachment; filename=edysor_digest_<period>.pdf`.
    *   **Storage Query**: Uploads PDF buffer to GCS under path `reports/edysor_digest_<period>.pdf` using `uploadToGCS`.

*   **`GET /api/v1/reports/audit-alerts-24h`** (Line 1805)
    *   **Parameters**: None.
    *   **Response Structure**: JSON file attachment. Sets headers `Content-Type: application/json` and `Content-Disposition: attachment; filename=edysor_audit_alerts_24h.json`. Contains filtered alert elements and system status info.
    *   **Database Query**: In-memory filter on `alerts` timestamp.

---

### Python Service Mappings
The following real service classes and files were identified in `C:\Users\ijain\AI_SOC_2\intelligence_engine`:

| Monolithic Node Logic | Python Target Module & Class | Context & Implementation Details |
|---|---|---|
| **`/api/v1/investigate`** | `agents/investigation_agent.py` → `build_investigation_graph` | Defines a LangGraph workflow with `planner_node`, `identity_investigation_node`, `malware_investigation_node`, `hypothesis_node`, `attack_reconstruction_node`, and `decision_node`. |
| **`/api/v1/investigation/explain`** | `main.py` → `investigation_explain` | Exposes a FastAPI endpoint `/api/v1/investigation/explain` using `ChatGoogleGenerativeAI(model="gemini-1.5-pro")` to generate an investigation scenario explanation. |
| **`/api/v1/copilot/query`** | `main.py` → `copilot_query` | Exposes a FastAPI endpoint `/api/v1/copilot/query` using Gemini (`gemini-1.5-pro`) to provide structured query answers, evidence, confidence, and MITRE mapping. |
| **`/api/v1/incidents/:id/predict-risk`** | `agents/triage_agent.py` → `triage_agent` | Runs an autonomous triage engine evaluating alert telemetry risk (0-100), severity, and confidence via GraphRAG context. |
| **`/api/v1/incidents/:id/recommended-triage`** | `agents/soc_orchestrator.py` → `triage_node` | Orchestrates delegation to the triage agent and sets risk context. |
| **`/api/v1/reports/digest`** | `reporting/report_generator.py` → `ReportGenerator` | Class containing `generate_executive_report` (returns markdown) and `generate_technical_report` (returns JSON structure). |

---

### Database Query Structures in Python Engine
The Python intelligence engine runs actual PostgreSQL (and mock ClickHouse) operations:

#### 1. PostgreSQL Schema & Queries

*   **`security_events` Table** (Used in `agents/investigation_agent.py` - Line 66)
    *   *Select Query*:
        ```sql
        SELECT * FROM security_events WHERE entity = %s ORDER BY timestamp DESC LIMIT 10
        ```
*   **`agent_decisions` Table** (Used in `agents/investigation_agent.py` - Line 171)
    *   *Insert Query*:
        ```sql
        INSERT INTO agent_decisions (investigation_id, observation, evidence_references, mitre_mapping, risk_score, decision_taken)
        VALUES (%s, %s, %s, %s, %s, %s)
        ```
*   **`incident_memory` Table** (Used in `core/memory_learning.py` - Line 17, 41, 90)
    *   *Schema*:
        ```sql
        CREATE TABLE IF NOT EXISTS incident_memory (
            id SERIAL PRIMARY KEY,
            incident_id VARCHAR(255) NOT NULL,
            incident_data JSONB NOT NULL,
            resolution_status VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ```
    *   *Insert Query*:
        ```sql
        INSERT INTO incident_memory (incident_id, incident_data, resolution_status)
        VALUES (%s, %s, %s) RETURNING id
        ```
    *   *Select Query*:
        ```sql
        SELECT incident_id, incident_data, resolution_status FROM incident_memory WHERE incident_id = %s
        ```
*   **`action_approvals` Table** (Used in `core/memory_learning.py` - Line 25, 52, 63, 72)
    *   *Schema*:
        ```sql
        CREATE TABLE IF NOT EXISTS action_approvals (
            id SERIAL PRIMARY KEY,
            incident_id VARCHAR(255) NOT NULL,
            suggested_action JSONB NOT NULL,
            status VARCHAR(50) DEFAULT 'PENDING',
            human_feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ```
    *   *Insert Query*:
        ```sql
        INSERT INTO action_approvals (incident_id, suggested_action, status)
        VALUES (%s, %s, 'PENDING') RETURNING id
        ```
    *   *Update Query*:
        ```sql
        UPDATE action_approvals SET status = %s, human_feedback = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s
        ```
    *   *Select Query*:
        ```sql
        SELECT id, incident_id, suggested_action, status, human_feedback FROM action_approvals WHERE status = 'PENDING'
        ```
*   **`response_actions` Table** (Used in `soar/automation_engine.py` - Line 16)
    *   *Insert Query*:
        ```sql
        INSERT INTO response_actions (timestamp, risk_score, action, status, api_response)
        VALUES (%s, %s, %s, %s, %s)
        ```

#### 2. ClickHouse Schema & Queries
*   **`soc_events` Table** (Used in `core/clickhouse_writer.py` - Line 38)
    *   *Insert Call (buffered)*:
        ```python
        self.client.insert('soc_events', self.buffer)
        ```

---

## 2. Logic Chain
1. **Endpoint Analysis**: By inspecting `server.js` with `view_file` (Lines 926–1438 and 1774–1832), we directly identified the HTTP verbs, paths, parameter parsing rules (e.g. `parseInt(req.params.id)`), response structures, and external cloud integrations (like Google Cloud Storage via the `uploadToGCS` helper).
2. **Proxying & Mapping**: By observing proxy routes (Lines 2004–2037 in `server.js`), we confirmed that `server.js` forwards `/api/v1/investigate` and `/api/v1/investigation/explain` calls to the Python backend via `proxyToIntelligenceEngine`.
3. **Python Mappings**: Examining `main.py` in the `intelligence_engine` directory verified that it listens on `/api/v1/investigate` and `/api/v1/investigation/explain`. Tracing imported elements and module layout confirmed that investigation logic maps to `agents/investigation_agent.py` and triage logic maps to `agents/triage_agent.py`/`agents/soc_orchestrator.py`.
4. **Database Logic Mapping**: Searching the Python files for SQL patterns and `clickhouse_connect` usage revealed that database schema setups and queries are executed in `agents/investigation_agent.py`, `core/memory_learning.py`, and `soar/automation_engine.py`. ClickHouse interaction is handled in `core/clickhouse_writer.py`.

---

## 3. Caveats
*   **Neo4j Graph Topology**: The Neo4j database topology contains static definitions that match the in-memory fallback. While the backend implements real Neo4j driver configurations, it gracefully falls back if environment credentials (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`) are omitted.
*   **Qdrant Vector Database**: Vector searches and insertions have default mock arrays if the Google Gemini API client or Qdrant connection is disabled.

---

## 4. Conclusion
The Monolithic Node.js routes for Alerts, Incidents, and Reports are prime candidates for FastAPI migration. The logical and database structures are fully audited. Real data mappings to PostgreSQL and ClickHouse are already implemented in python services (`investigation_agent.py`, `memory_learning.py`, `automation_engine.py`, `clickhouse_writer.py`) and can be seamlessly hooked into the new FastAPI endpoint routers.

---

## 5. Verification Method
1.  **FastAPI Endpoints**: Run the existing pytest suite for the python intelligence engine to verify the baseline FastAPI endpoints:
    ```bash
    cd C:\Users\ijain\AI_SOC_2\intelligence_engine
    pytest tests/test_main_api.py
    ```
2.  **Verify Files**: Inspect files directly:
    *   FastAPI entrypoint: `C:\Users\ijain\AI_SOC_2\intelligence_engine\main.py`
    *   LangGraph Investigation Graph: `C:\Users\ijain\AI_SOC_2\intelligence_engine\agents\investigation_agent.py`
    *   Triage Logic: `C:\Users\ijain\AI_SOC_2\intelligence_engine\agents\triage_agent.py`
