# 🔐 EDYSOR - Secret Management Plan

This document outlines the strategy for migrating from local `.env` files to Google Cloud Secret Manager for the **EDYSOR** platform. This ensures that no sensitive credentials are hardcoded or stored in plain text, complying with enterprise security standards.

---

## 1. Secret Mapping Matrix

The following table maps the local environment variables to their corresponding Google Cloud Secret Manager keys.

| Application Environment Variable | Cloud Secret Name | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | `GEMINI_API_KEY` | Authentication key for Google GenAI (Gemini Swarm). |
| `QDRANT_API_KEY` | `QDRANT_API_KEY` | API token for the Qdrant Vector Database. |
| `NEO4J_PASSWORD` | `NEO4J_PASSWORD` | Password for the Neo4j Graph Database. |
| `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD` | Password for the Cloud SQL PostgreSQL instance. |
| `JWT_SECRET` | `JWT_SECRET` | Cryptographic secret used for signing user session tokens. |
| `SMTP_PASSWORD` | `SMTP_PASSWORD` | Credentials for sending automated email alerts. |

*Note: Non-sensitive configurations like URLs (`QDRANT_URL`, `NEO4J_URI`) or usernames (`POSTGRES_USER`, `NEO4J_USERNAME`) can remain as standard environment variables injected at runtime, although passwords MUST be secrets.*

---

## 2. Creating Secrets in Secret Manager

Execute the following commands to create the secret placeholders in Google Cloud Secret Manager. (You will be prompted or expected to add the actual values via the GCP Console or files).

```bash
# Set your project ID
export PROJECT_ID="edysor-production"

# Create secrets
gcloud secrets create GEMINI_API_KEY --replication-policy="automatic"
gcloud secrets create QDRANT_API_KEY --replication-policy="automatic"
gcloud secrets create NEO4J_PASSWORD --replication-policy="automatic"
gcloud secrets create POSTGRES_PASSWORD --replication-policy="automatic"
gcloud secrets create JWT_SECRET --replication-policy="automatic"
gcloud secrets create SMTP_PASSWORD --replication-policy="automatic"

# Example: Adding a value from a local file
# gcloud secrets versions add GEMINI_API_KEY --data-file="/path/to/gemini_key.txt"
```

---

## 3. Configuring Secret Access (IAM)

The application running in Cloud Run needs the `roles/secretmanager.secretAccessor` role to read these secrets. This was provisioned in Milestone 2 for the `edysor-app-sa` Service Account.

To verify or grant access to specific secrets instead of project-wide (Least Privilege):

```bash
export APP_SA="edysor-app-sa@${PROJECT_ID}.iam.gserviceaccount.com"

for SECRET in GEMINI_API_KEY QDRANT_API_KEY NEO4J_PASSWORD POSTGRES_PASSWORD JWT_SECRET SMTP_PASSWORD; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${APP_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
done
```

---

## 4. Runtime Secret Loading in Cloud Run

Google Cloud Run natively supports mounting Secret Manager secrets as environment variables at runtime. This means `server.js` does not need to use the Google Cloud SDK to fetch secrets; it simply reads `process.env.GEMINI_API_KEY` as if it were a local `.env` file.

When deploying the Cloud Run service, secrets are mapped directly to environment variables:

```bash
gcloud run deploy edysor-backend \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/edysor-repo/soc-backend:latest \
  --service-account=$APP_SA \
  --set-env-vars="DB_TYPE=postgres,POSTGRES_HOST=127.0.0.1,POSTGRES_USER=soc,POSTGRES_DB=soc" \
  --set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest,\
QDRANT_API_KEY=QDRANT_API_KEY:latest,\
NEO4J_PASSWORD=NEO4J_PASSWORD:latest,\
POSTGRES_PASSWORD=POSTGRES_PASSWORD:latest,\
JWT_SECRET=JWT_SECRET:latest,\
SMTP_PASSWORD=SMTP_PASSWORD:latest" \
  --region=$REGION
```

### Validation Checks
1. Ensure `.env` is listed in `.gitignore` (and `.dockerignore`) to prevent accidental commits.
2. During the CI/CD pipeline build phase, verify that no secret variables are baked into the Docker image.
3. Validate runtime access by checking the Cloud Logging console upon the first deployment for any `PermissionDenied` errors related to the Secret Manager.
