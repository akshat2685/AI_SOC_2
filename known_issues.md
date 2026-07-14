# ShieldAI SOC Platform: Known Issues & Limitations
**Milestone 12 - Documentation & Handover**

## 1. AI Provider Instability (Gemini API 503s)
*   **Issue:** During periods of extremely high global demand, the Gemini API may return `503 Service Unavailable` or `429 Too Many Requests`.
*   **Impact:** GraphRAG chat queries and Agentic Task Routing will fail to generate dynamic insights.
*   **Workaround:** The application currently catches these errors and returns a formatted warning string rather than crashing.
*   **Long-term Fix:** Transition from on-demand pricing to Provisioned Throughput in Google Cloud to guarantee SLA and capacity. Implement exponential backoff and retry logic in the orchestration layer.

## 2. WebSocket Connection Drops
*   **Issue:** Cloud Run (Gen2) supports WebSockets, but idle connections may be terminated by the load balancer after 1 hour or during container scaling events.
*   **Impact:** The real-time telemetry feed on the frontend may disconnect.
*   **Workaround:** The frontend client must implement robust reconnection logic (e.g., `socket.io-client` handles this automatically, but raw WebSockets require custom reconnect loops).

## 3. High Dimensionality Vector Overhead
*   **Issue:** Qdrant search latency slightly increases when applying complex payload filters alongside dense vector search.
*   **Impact:** Semantic searches with deep tenant-isolation filters might exceed 50ms latency.
*   **Workaround:** Ensure payload indexes are explicitly created in Qdrant for fields frequently used in filters (e.g., `tenant_id`, `severity`).

## 4. In-Memory Rate Limiter Reset
*   **Issue:** `express-rate-limit` currently stores hit counts in-memory. In a distributed Cloud Run environment with multiple instances, rate limits are per-instance, not global.
*   **Impact:** A user hitting the API through a load balancer that round-robins across 5 instances effectively has 5x the intended rate limit.
*   **Workaround:** For strict global rate limiting, transition the `express-rate-limit` store to a shared Redis instance (e.g., Memorystore).
