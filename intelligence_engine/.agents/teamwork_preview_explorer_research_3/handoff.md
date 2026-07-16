# Handoff Report — Route Mapping Analysis

## 1. Observation

A comprehensive code audit of the monolithic Node.js backend (`server.js`) and the Python intelligence engine (`intelligence_engine`) was conducted.

### Monolith Route Configurations (`C:\Users\ijain\AI_SOC_2\server.js`):
1. **Integration Status:**
   - Path & Method: `GET /api/v1/integrations/status` (Line 1538)
   - Functionality: Pings Neo4j and Qdrant databases and reports connection status and record counts.
2. **Integration Sync:**
   - Path & Method: `POST /api/v1/integrations/sync` (Line 1586)
   - Functionality: Triggers seeding functions `seedNeo4j()` and `seedQdrant()`.
3. **Threat Intel CVE:**
   - Path & Method: `GET /threat-intel/cve/:cveId` (Line 1704)
4. **Threat Intel IP:**
   - Path & Method: `GET /threat-intel/ip/:ip` (Line 1714)
5. **Threat Intel Sync:**
   - Path & Method: `POST /threat-intel/sync` (Line 1725)
6. **Threat Intel KEV Sync:**
   - Path & Method: `POST /threat-intel/kev/sync` (Line 1729)
7. **Threat Intel PDF Report:**
   - Path & Method: `GET /threat-intel/report.pdf` (Line 1834)
8. **Storage File Upload:**
   - Path & Method: `POST /api/v1/storage/upload` (Line 1763)
   - Functionality: Saves form-data files to Google Cloud Storage.
9. **Alert PDF Report:**
   - Path & Method: `GET /alerts/:alertId/report.pdf` (Line 1774)
10. **Reports Digest:**
    - Path & Method: `GET /api/v1/reports/digest` (Line 1789)
11. **Firewall Block Status:**
    - Path & Method: `GET /api/v1/firewall/blocks` (Line 1644)
12. **Firewall Block IP:**
    - Path & Method: `POST /api/v1/firewall/block` (Line 1648)
13. **Firewall Unblock IP:**
    - Path & Method: `POST /api/v1/firewall/unblock` (Line 1680)
14. **Approvals List:**
    - Path & Method: `GET /approvals` (Line 1874)
15. **Incident Recommended Triage:**
    - Path & Method: `GET /api/v1/incidents/:id/recommended-triage` (Line 1073)

### Python Intelligence Engine Structures (`C:\Users\ijain\AI_SOC_2\intelligence_engine`):
1. **Connectors:**
   - Abstract Base Class: `BaseConnector` in `connectors/base.py` (Line 32)
   - SIEM: `WazuhConnector` in `connectors/siem/wazuh.py` (Line 74), `SplunkConnector` in `connectors/splunk.py` (Line 3), and `SentinelConnector` in `connectors/sentinel.py` (Line 3).
   - Cloud: `AWSCloudTrailConnector` in `connectors/cloud/aws_cloudtrail.py` (Line 3), `AzureIAMConnector` in `connectors/cloud/azure_iam.py` (Line 1).
   - Identity: `OktaConnector` in `connectors/identity/okta.py` (Line 1), `GoogleWorkspaceConnector` in `connectors/identity/google_workspace.py` (Line 1).
   - Network: `PaloAltoAdapter` in `connectors/network/paloalto_adapter.py` (Line 3), `ZeekAdapter` in `connectors/network/zeek_adapter.py` (Line 3).
   - EDR: `CrowdStrikeAdapter` in `connectors/edr/crowdstrike_adapter.py` (Line 3), `DefenderAdapter` in `connectors/edr/defender_adapter.py` (Line 3).
2. **Playbooks & SOAR:**
   - Engines: `SOARAutomationEngine` in `soar/automation_engine.py` (Line 6) and `PlaybookEngine` in `soar/playbook_engine.py` (Line 3).
   - Connectors: `EndpointConnector` in `soar/connectors/endpoint.py` (Line 3), `FirewallConnector` in `soar/connectors/firewall.py` (Line 3), `IdentityConnector` in `soar/connectors/identity.py` (Line 3), and `TicketConnector` in `soar/connectors/ticket.py` (Line 3).

---

## 2. Logic Chain

1. **Integrations Route & Status Mapping:**
   - The route `GET /api/v1/integrations/status` uses database driver/client properties `neo4jDriver` and `qdrantClient` to verify connections.
   - In Python, `core/health.py` defines `HealthChecker` with methods `check_neo4j()` and `check_qdrant()`. These functions calculate latency and status (Lines 21, 28) and aggregate results (`aggregate()` on Line 49).
   - The status route maps to the health monitoring services of `HealthChecker` and specific connectors' health lifecycles (e.g., `WazuhConnector.health()` on Line 139).
2. **Database Sync Seeding:**
   - `POST /api/v1/integrations/sync` triggers `seedNeo4j()` and `seedQdrant()` in Node.js.
   - Seeding routes map to graph construction in `graph/neo4j_reasoning.py` and vector indexing initialization in `core/memory_learning.py` and `memory/experience_replay.py`.
3. **SOAR / Playbook Execution Mapping:**
   - The route `GET /api/v1/incidents/:id/recommended-triage` responds with containment recommendations and playbooks (e.g., lines 1165-1215 in `server.js`).
   - In the Python engine, `soar/playbook_engine.py` contains `PlaybookEngine.execute_playbook()` which matches alerts to playbooks (like `Credential Attack` or `Malware`) and schedules actions requiring approval (Lines 8-10).
   - Firewall block/unblock requests (`POST /api/v1/firewall/block` and `POST /api/v1/firewall/unblock`) map to the actions implemented in `soar/connectors/firewall.py:FirewallConnector` (`block_ip` on Line 5, `unblock_ip` on Line 10).
   - Approved actions and automated containment are monitored by `SOARAutomationEngine` in `soar/automation_engine.py`, which evaluates risk scores and enforces execution policies (Line 33).
4. **Storage Integration Mapping:**
   - The Node.js route `POST /api/v1/storage/upload` handles file streams using GCP `Storage` (Line 1736) and uploads binary data into GCS (`uploadToGCS` Line 1747).
   - In the Python engine, there is no active storage service implementation. The route logic must map to a planned `GoogleCloudStorageService` in a new module, e.g. `intelligence_engine/core/storage.py`, interacting with the `google-cloud-storage` Python SDK.

---

## 3. Caveats

1. **In-Memory Approvals and Blocks:** The Node.js `server.js` stores `approvals` and `firewallBlocks` arrays only in-memory (Line 752 and Line 1624). In a production FastAPI migration, these should persist to the PostgreSQL database (`response_actions` or similar tables) or Redis.
2. **Missing Python Storage Engine:** There is currently no file or class in the Python project (`intelligence_engine`) that corresponds to storage/GCS interaction. A new storage module must be created during Milestone 6.
3. **No Direct /api/v1/playbooks Endpoint:** There are no endpoints named `/api/v1/playbooks` or `/api/v1/soar` in `server.js`. The playbook/SOAR capabilities are exposed via `/api/v1/incidents/:id/recommended-triage`, `/approvals`, and `/api/v1/firewall/*`.

---

## 4. Conclusion

The monolith backend has clear endpoints for integration status, threat intel, storage uploads, firewall blocking, and approvals. They map cleanly to Python service classes (such as `HealthChecker`, `PlaybookEngine`, `SOARAutomationEngine`, and adapters inside `connectors/` and `soar/connectors/`).
Below is the definitive schema mapping of the audited endpoints:

### Endpoint Schema & Component Dependency Map

| Area | HTTP Method & Path | Inputs (Path / Query / Body) | Output Structure | Active Component Dependencies | Mapped Python Service Class |
|---|---|---|---|---|---|
| **Connectors & Integrations** | `GET /api/v1/integrations/status` | None | `{ neo4j: { connected, uri, database, nodesCount }, qdrant: { connected, url, pointsCount } }` | `neo4jDriver`, `qdrantClient` | `core/health.py:HealthChecker` |
| **Connectors & Integrations** | `POST /api/v1/integrations/sync` | None | `{ success: boolean, message: string }` | `neo4jDriver` (seeds topology), `qdrantClient` (seeds collections) | `graph/neo4j_reasoning.py`, `core/memory_learning.py` |
| **Threat Intel** | `GET /threat-intel/cve/:cveId` | `cveId` (Path) | `{ cve_id, description, cvss_score, published_at, remediation }` | None (Mocked response) | `core/ioc_extractor.py` (planned intel service) |
| **Threat Intel** | `GET /threat-intel/ip/:ip` | `ip` (Path) | `{ ip, reputation, score, country, asn, recent_detections }` | None (Mocked response) | `core/ioc_extractor.py` (planned intel service) |
| **Threat Intel** | `POST /threat-intel/sync` | None | `{ status, message }` | None (Mocked response) | None |
| **Threat Intel** | `POST /threat-intel/kev/sync` | None | `{ status, message }` | None (Mocked response) | None |
| **Threat Intel** | `GET /threat-intel/report.pdf` | None | PDF File Stream | `GCS_BUCKET_NAME` | `core/storage.py:GoogleCloudStorageService` (Planned) |
| **SOAR & Playbooks** | `GET /api/v1/incidents/:id/recommended-triage` | `id` (Path) | `{ similarIncidents: [...], threatIntel: {...}, recommendedPlaybooks: [{ name, steps, matchReason }] }` | Intelligence Engine API proxy (or in-memory mock fallback) | `soar/playbook_engine.py:PlaybookEngine`, `soar/automation_engine.py:SOARAutomationEngine` |
| **SOAR & Playbooks** | `GET /approvals` | None | Array of approvals: `[{ id, timestamp, title, action, target, requested_by, status, justification }]` | In-memory `approvals` array | `soar/playbook_engine.py:PlaybookEngine.pending_approvals` |
| **SOAR & Playbooks** | `GET /api/v1/firewall/blocks` | None | Array of blocks: `[{ ip, type, hours, reason, timestamp }]` | In-memory `firewallBlocks` array | `soar/connectors/firewall.py:FirewallConnector` |
| **SOAR & Playbooks** | `POST /api/v1/firewall/block` | `ip` (Body, Req), `type`, `hours`, `reason` (Body, Opt) | `{ success, message, entry: { ip, type, hours, reason, timestamp } }` | Modifies in-memory arrays `firewallBlocks` & `auditLogs` | `soar/connectors/firewall.py:FirewallConnector.block_ip` |
| **SOAR & Playbooks** | `POST /api/v1/firewall/unblock` | `ip` (Body, Req) | `{ success, message }` | Filters in-memory arrays `firewallBlocks` & `auditLogs` | `soar/connectors/firewall.py:FirewallConnector.unblock_ip` |
| **Storage** | `POST /api/v1/storage/upload` | `file` (Multipart Body, Req) | `{ status, url, filename }` | Google Cloud Storage SDK client, `GCS_BUCKET_NAME`, `multer` (50MB limit) | `core/storage.py:GoogleCloudStorageService` (Planned) |
| **Storage** | `GET /alerts/:alertId/report.pdf` | `alertId` (Path) | PDF File Stream | GCS bucket (`reports/edysor_alert_[alertId].pdf`) | `core/storage.py:GoogleCloudStorageService` (Planned) |
| **Storage** | `GET /api/v1/reports/digest` | `period` (Query, Opt) | PDF File Stream | GCS bucket (`reports/edysor_digest_[period].pdf`) | `core/storage.py:GoogleCloudStorageService` (Planned) |

---

## 5. Verification Method

To verify the route mapping logic and Python services:
1. **Pytest suite:** Run `pytest` within `C:\Users\ijain\AI_SOC_2\intelligence_engine` directory to verify tests for SOAR and other modules.
   - `test_agents.py` verifies policy logic in `SOARAutomationEngine`.
   - `test_main_api.py` mocks copilot API and response behavior.
2. **Configuration Settings inspection:** Inspect the Pydantic configurations in `C:\Users\ijain\AI_SOC_2\intelligence_engine\core\config.py` to check standard environment variables.
