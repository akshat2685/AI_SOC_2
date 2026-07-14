# ShieldAI SOC Platform: Rollback Plan
**Milestone 12 - Documentation & Handover**

## 1. Purpose
This document outlines the procedures for rolling back the ShieldAI SOC Platform in the event of a critical failure following a production deployment.

## 2. Triggers for Rollback
A rollback should be initiated if any of the following occur within the first hour of a new deployment:
*   Subsystem failure rate exceeds 5% (e.g., persistent HTTP 500s).
*   Container crash loop or failure to start (Health Check `/health` failing).
*   Severe latency degradation (P95 > 2 seconds).
*   Critical security vulnerability discovered in the newly deployed code.
*   Data corruption or schema mismatch causing widespread query failures.

## 3. Rollback Procedures

### 3.1 Application Code Rollback (Cloud Run)
Because Google Cloud Run maintains immutable revisions, rolling back the application layer is near-instantaneous.
1.  **Identify Target Revision:** Access the Cloud Run console or use the gcloud CLI to list recent revisions.
2.  **Execute Rollback:**
    ```bash
    gcloud run services update-traffic shieldai-soc --to-revisions=shieldai-soc-[PREVIOUS_REVISION_ID]=100
    ```
3.  **Verify:** Monitor the `/health` endpoint and Cloud Logging to confirm the old revision is handling traffic smoothly.

### 3.2 Database Schema Rollback
*   **Relational Database:** Apply the down-migration script using the configured ORM/migration tool. *Warning: Ensure data backups exist before rolling back destructive schema changes.*
*   **Neo4j Graph:** Use Cypher to revert any new labels or relationships introduced.
*   **Qdrant Vector DB:** If payload schemas changed, restore from the latest Qdrant snapshot.

### 3.3 Environment Variables & Secrets
If a deployment involved secret rotation that caused issues:
1.  Revert the secret version in Google Cloud Secret Manager.
2.  Redeploy or restart the Cloud Run revision to pick up the restored secret payload.

## 4. Post-Rollback Actions
*   **Notify Stakeholders:** Update the engineering and SOC teams regarding the rollback.
*   **Incident Report:** Document the root cause of the deployment failure and the timeline of the rollback.
*   **Fix & Forward:** Implement the fix in the staging environment before attempting redeployment.
