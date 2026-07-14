# ☁️ EDYSOR - Google Cloud Foundation Plan

This document outlines the foundational steps and scripts required to provision the Google Cloud project for the **EDYSOR** platform. This milestone establishes the necessary APIs, networking, IAM roles, and core services.

---

## 1. Project Initialization & Verification

First, ensure you are authenticated and have selected the correct Google Cloud Project.

```bash
# Authenticate with Google Cloud
gcloud auth login

# Set your project ID (replace with your actual project ID)
export PROJECT_ID="edysor-production"
gcloud config set project $PROJECT_ID

# Verify the current project
gcloud config get-value project
```

## 2. Region Configuration

Set the default region and zone for the deployment. This ensures that services like Cloud Run, Cloud SQL, and Artifact Registry are co-located to minimize latency.

```bash
export REGION="us-central1"
export ZONE="us-central1-a"

gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE
```

## 3. Enable Required APIs

Enable the necessary Google Cloud APIs for the EDYSOR architecture.

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudbuild.googleapis.com \
  compute.googleapis.com
```

## 4. Service Account Creation & IAM Configuration

Create dedicated service accounts following the principle of least privilege.

### A. Core Application Service Account (Cloud Run)

This service account will be used by the EDYSOR backend and frontend services running on Cloud Run.

```bash
# Create the service account
gcloud iam service-accounts create edysor-app-sa \
    --description="Service account for EDYSOR Cloud Run services" \
    --display-name="EDYSOR Application SA"

export APP_SA="edysor-app-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant necessary roles to the App Service Account
# 1. Access to Cloud SQL (Client)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${APP_SA}" \
    --role="roles/cloudsql.client"

# 2. Access to Secret Manager (Secret Accessor)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${APP_SA}" \
    --role="roles/secretmanager.secretAccessor"

# 3. Access to write Logs and Metrics
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${APP_SA}" \
    --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${APP_SA}" \
    --role="roles/monitoring.metricWriter"
```

### B. CI/CD Deployment Service Account (GitHub Actions / Cloud Build)

This account will handle pushing images to Artifact Registry and deploying to Cloud Run.

```bash
gcloud iam service-accounts create edysor-deploy-sa \
    --description="Service account for EDYSOR CI/CD pipeline" \
    --display-name="EDYSOR Deployment SA"

export DEPLOY_SA="edysor-deploy-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant roles for deployment
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DEPLOY_SA}" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DEPLOY_SA}" \
    --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DEPLOY_SA}" \
    --role="roles/iam.serviceAccountUser"
```

## 5. Artifact Registry Setup

Create a repository to store Docker images for the EDYSOR services.

```bash
gcloud artifacts repositories create edysor-repo \
    --repository-format=docker \
    --location=$REGION \
    --description="Docker repository for EDYSOR images"
```

## 6. Secret Manager Initialization

Create placeholders for critical secrets. These will be populated securely by administrators.

```bash
# Database Password
gcloud secrets create POSTGRES_PASSWORD --replication-policy="automatic"

# Gemini API Key
gcloud secrets create GEMINI_API_KEY --replication-policy="automatic"

# JWT Secret
gcloud secrets create JWT_SECRET --replication-policy="automatic"

# (Optional) Add a secret value from a file (e.g., jwt_secret.txt)
# gcloud secrets versions add JWT_SECRET --data-file="jwt_secret.txt"
```

## 7. Billing Dependencies Verification

Ensure that billing is linked to the project, as services like Cloud Run and Cloud SQL require an active billing account.

```bash
# List available billing accounts
gcloud billing accounts list

# Check if the project is linked to a billing account
gcloud billing projects describe $PROJECT_ID
```
If billing is not enabled, link it using the Google Cloud Console or the CLI.

---
**Status**: 🟢 Milestone 2 Foundation configuration is planned and ready for execution via standard GCP tooling.
