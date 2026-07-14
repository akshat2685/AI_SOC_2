# ShieldAI SOC Platform: Deployment Report
**Milestone 12 - Documentation & Handover**

## 1. Deployment Overview
This document summarizes the deployment state of the ShieldAI SOC Platform following the successful completion of end-to-end production verification. The application is deployed via Google Cloud Run, utilizing external managed services for its database and AI layers.

## 2. Environments
*   **Production Environment:**
    *   **Compute:** Google Cloud Run (Gen2)
    *   **Region:** `asia-southeast1` (Singapore)
    *   **Scaling:** 0 to 10 instances (auto-scaling enabled)
*   **Preview / Staging:** AI Studio Preview Environment

## 3. Infrastructure & Dependencies
| Service | Provider | Status | Purpose |
| :--- | :--- | :--- | :--- |
| **API Backend** | Google Cloud Run | **Live** | Express.js REST/WebSocket server |
| **Graph Database** | Neo4j AuraDB | **Live** | Security knowledge graph & topology |
| **Vector Database** | Qdrant Cloud | **Live** | High-dimensional semantic RAG memory |
| **AI Orchestration**| Google Gemini API | **Live** | Multi-agent task routing and analysis |
| **Secrets Mgt.** | GCP Secret Manager| **Live** | Secure credential storage |

## 4. Deployment Pipeline
The application currently utilizes a containerized deployment approach:
1.  **Code Commit:** Changes merged to `main` branch.
2.  **Build Phase:** Docker container built via Cloud Build (`npm run build` & `npm start`).
3.  **Deployment:** Image pushed to Artifact Registry and deployed to Cloud Run.
4.  **Verification:** Automated health checks (`/health`) validate container start before routing traffic.

## 5. Security & Network Posture
*   **Ingress:** HTTPS only (TLS 1.2+).
*   **Rate Limiting:** Active (100 req/min for standard APIs, 10 req/min for AI Agents).
*   **Headers:** Helmet configured (HSTS, CSP, X-Frame-Options).

## 6. Final Sign-off
The platform has passed all load, security, and integration tests. It is approved for production traffic.
