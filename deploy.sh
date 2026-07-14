#!/bin/bash
set -e

# Configuration
PROJECT_ID="your-google-cloud-project-id"
REGION="us-central1"
SERVICE_NAME="shieldai-soc"
# Using Artifact Registry instead of Container Registry
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}:latest"

echo "Building Docker image..."
# Build the Docker image
# Depending on your setup, you can use Google Cloud Build directly:
gcloud builds submit --tag ${IMAGE_NAME} .
# Or build locally and push (requires docker auth):
# docker build -t ${IMAGE_NAME} .
# docker push ${IMAGE_NAME}

echo "Deploying to Cloud Run..."
# Deploy to Cloud Run
# Notice: Cloud Run injects the PORT automatically. We use Secret Manager for secrets instead of hardcoding them.
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "NODE_ENV=production" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,POSTGRES_USER=postgres-user:latest,POSTGRES_PASSWORD=postgres-password:latest,POSTGRES_DB=postgres-db:latest,POSTGRES_HOST=postgres-host:latest,POSTGRES_PORT=postgres-port:latest,GCS_BUCKET_NAME=gcs-bucket-name:latest,NEO4J_URI=neo4j-uri:latest,NEO4J_USERNAME=neo4j-username:latest,NEO4J_PASSWORD=neo4j-password:latest,QDRANT_URL=qdrant-url:latest,QDRANT_API_KEY=qdrant-api-key:latest" \
  --min-instances 1 \
  --max-instances 10 \
  --cpu 2 \
  --memory 2Gi \
  --timeout 300 \
  --concurrency 80 \
  --cpu-boost \
  --execution-environment gen2 \
  --liveness-probe=path=/health,initialDelaySeconds=30,periodSeconds=20,timeoutSeconds=5,failureThreshold=3 \
  --startup-probe=path=/health,initialDelaySeconds=30,periodSeconds=15,timeoutSeconds=5,failureThreshold=15

echo "Deployment completed successfully!"
