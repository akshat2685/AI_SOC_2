# Production Deployment Guide

## Architecture Overview
The ShieldAI SOC system consists of:
- **Backend API Server**: FastAPI service handling REST endpoints, auth, and dispatching background tasks.
- **Worker Subsystem**: Asynchronous Kafka consumer and LangGraph orchestrator engine processing security events.
- **Data Persistence**: PostgreSQL (Relational schema), ClickHouse (High-throughput telemetry), Neo4j (GraphRAG blast-radius reasoning).

## Deployment Options

### Option 1: Docker Compose Production Stack
```bash
# 1. Copy environment file and fill secrets
cp backend/.env.example .env

# 2. Build and launch services
docker compose -f docker-compose.prod.yml up -d --build

# 3. Run database migrations
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### Option 2: Kubernetes (Helm / Manifests)
```bash
# Apply database migrations
alembic upgrade head

# Deploy manifests
kubectl apply -f k8s/
```
