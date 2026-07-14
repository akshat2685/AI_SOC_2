# ShieldAI SOC Platform: Operations Runbook
**Milestone 12 - Documentation & Handover**

## 1. Overview
This runbook provides operational guidelines for maintaining, monitoring, and troubleshooting the ShieldAI SOC Platform in a production environment.

## 2. Monitoring & Observability

### 2.1 Key Metrics to Watch (GCP Metrics Explorer)
*   `run.googleapis.com/request_count`: Total traffic volume. Watch for sudden unexplained spikes.
*   `run.googleapis.com/request_latencies`: API response times. Alert if P95 exceeds 1000ms.
*   `run.googleapis.com/container/memory/utilizations`: Ensure containers are not exceeding the 2GiB limit.
*   `run.googleapis.com/container/instance_count`: Track auto-scaling behavior.

### 2.2 Logging
*   All application logs are routed to **Google Cloud Logging**.
*   Filter by `severity=ERROR` to find unhandled exceptions or failed API calls.
*   Search `textPayload:"[QDRANT]"` or `textPayload:"[NEO4J]"` to isolate database integration issues.

## 3. Common Incident Responses

### Incident: Gemini API Quota Exceeded (HTTP 429)
*   **Symptoms:** Chat UI displays errors; Agent tasks fail to complete; Logs show Gemini SDK throwing 429 errors.
*   **Action:** 
    1. Check GCP Quotas page for Generative Language API.
    2. If legitimate traffic caused the spike, request a quota increase.
    3. Verify rate limiters in Express are functioning to prevent abuse.

### Incident: Neo4j Connection Refused
*   **Symptoms:** Graph topology endpoints return empty or 500 errors.
*   **Action:**
    1. Verify AuraDB instance status in the Neo4j console.
    2. Check Secret Manager to ensure the `NEO4J_PASSWORD` hasn't expired or been rotated without a container restart.
    3. Restart the Cloud Run service to force a new connection pool initialization.

### Incident: High Latency Spikes
*   **Symptoms:** Dashboard loading times exceed 3 seconds.
*   **Action:**
    1. Check Cloud Trace to identify the bottleneck (is it the DB, or the AI provider?).
    2. If DB, check index health.
    3. If CPU bound, consider increasing Cloud Run CPU allocation or adjusting concurrency settings.

## 4. Routine Maintenance Tasks
*   **Weekly:** Review Cloud Security Command Center for new vulnerabilities in dependencies.
*   **Monthly:** Rotate Qdrant and Neo4j API keys. Update Secret Manager and redeploy the Cloud Run service.
*   **Quarterly:** Review and prune stale Vector data in Qdrant to optimize memory usage.
