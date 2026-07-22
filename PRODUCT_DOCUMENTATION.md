# 🛡️ ShieldAI / EDYSOR Autonomous AI SOC Platform
## Enterprise Product Documentation & Operations Manual

---

## 1. Product Description

### Overview
**ShieldAI (EDYSOR)** is an autonomous, AI-driven Security Operations Center (SOC) platform engineered for real-time threat detection, automated incident triage, dynamic attack path reasoning, and automated playbook orchestration. 

By combining high-throughput telemetry ingestion, graph-based attack visualization, vector search, and Generative AI (LLMs), ShieldAI reduces Mean Time to Detect (MTTD) and Mean Time to Respond (MTTR) from hours to seconds.

```
                  +----------------------------------------------+
                  |         ShieldAI Web Dashboard UI            |
                  |         (Port 80 / Grafana Port 3000)        |
                  +----------------------+-----------------------+
                                         |
                                         v
                  +----------------------+-----------------------+
                  |           FastAPI SOC Backend                |
                  |               (Port 8000)                    |
                  +-------+--------------+---------------+-------+
                          |              |               |
          +---------------+              v               +---------------+
          |                    +------------------+                      |
          v                    | Kafka Event Bus  |                      v
+------------------+           |   (Port 9092)    |            +------------------+
|  PostgreSQL DB   |           +--------+---------+            |     Redis DB     |
|   (Port 5432)    |                    |                      |   (Port 6379)    |
+------------------+                    v                      +------------------+
                               +------------------+
                               |   SIEM Worker    |
                               +--------+---------+
                                        |
     +----------------------------------+----------------------------------+
     |                                  |                                  |
     v                                  v                                  v
+------------------+           +------------------+           +------------------+
|  ClickHouse DB   |           |  Qdrant Vector   |           |    Neo4j Graph   |
|   (Port 8123)    |           |   (Port 6333)    |           |   (Port 7474)    |
+------------------+           +------------------+           +------------------+
                                        ^
                                        |
                               +--------+---------+
                               |     AI Layer     |
                               |   (Port 8001)    |
                               | (Gemini / Lang)  |
                               +------------------+
```

### Core Architecture Components
1. **Frontend Dashboard (`shieldai-frontend`)**: React/Nginx web interface providing live threat visualization, alert queues, and system telemetry monitoring.
2. **FastAPI Backend (`shieldai-soc`)**: Core REST API layer handling user management, RBAC, alert lifecycle, rule configuration, and orchestration dispatch.
3. **AI Intelligence Engine (`shieldai-ai-layer`)**: Multi-agent framework powered by LangChain/LangGraph and Gemini LLMs for automated threat triage, incident summary generation, and conversational security copilot.
4. **SIEM Telemetry Worker (`shieldai-worker`)**: High-speed Kafka log processor that executes machine learning anomaly detection and streams events to long-term storage.
5. **Data & Storage Layer**:
   - **PostgreSQL**: Primary transactional store for tenancy, alerts, and system state.
   - **ClickHouse**: Columnar datastore for massive-scale raw security event logs.
   - **Neo4j**: Graph database modeling network topography, user identity graphs, and attack chains.
   - **Qdrant**: High-performance vector database for semantic similarity search and RAG capabilities.
   - **Redis**: Low-latency cache and session store.
   - **Apache Kafka**: Distributed stream buffer for real-time telemetry events.
6. **Deception & Observability Grid**:
   - **Canaries / Honeypots**: Dionaea (FTP/SMB) and Cowrie (SSH/Telnet) threat capture.
   - **Monitoring Stack**: Prometheus metrics collection, Grafana dashboards, Jaeger OTLP distributed tracing, and HashiCorp Vault secrets management.

---

## 2. Installation Guide

### Prerequisites (All Platforms)
- **Docker Desktop** (or Docker Engine v24.0+) & **Docker Compose v2.20+**
- Minimum System Hardware:
  - **CPU**: 4 Cores (8 Cores recommended)
  - **RAM**: 16 GB (32 GB recommended)
  - **Disk**: 40 GB free space
- Required Ports: `80`, `8000`, `8001`, `5432`, `6379`, `9092`, `8123`, `6333`, `7474`, `7687`, `9090`, `3000`, `8200`

---

### A. Windows Installation

1. **Install Prerequisites**:
   - Download and install **Docker Desktop for Windows** (WSL 2 backend enabled).
   - Install **Git** and **Python 3.11+**.

2. **Clone the Repository**:
   ```powershell
   git clone https://github.com/akshat2685/AI_SOC_2.git
   cd AI_SOC_2
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GOOGLE_API_KEY=your_google_api_key_here
   POSTGRES_PASSWORD=changeme_in_production
   CLICKHOUSE_PASSWORD=changeme_clickhouse
   JWT_SECRET=dev_secret_key_change_in_prod
   VAULT_TOKEN=root
   ```

4. **Launch the System**:
   ```powershell
   docker compose up -d --build
   ```

5. **Verify Deployment**:
   ```powershell
   docker ps
   ```
   All 17 containers should report `Up`. Access the dashboard at `http://localhost`.

---

### B. macOS Installation (Intel & Apple Silicon M1/M2/M3)

1. **Install Prerequisites**:
   - Install **Docker Desktop for Mac** (Enable *Use Rosetta 2 for x86_64 emulation* if on Apple Silicon).
   - Install Homebrew, Git, and Python:
     ```bash
     brew install git python@3.11
     ```

2. **Clone & Configure Environment**:
   ```bash
   git clone https://github.com/akshat2685/AI_SOC_2.git
   cd AI_SOC_2
   cp .env.example .env
   ```
   Edit `.env` to include your `GEMINI_API_KEY` and `GOOGLE_API_KEY`.

3. **Deploy Containers**:
   ```bash
   docker compose up -d --build
   ```

4. **Health Verification**:
   ```bash
   curl -I http://localhost/
   curl -I http://localhost:8000/docs
   ```

---

### C. Linux Installation (Ubuntu / Debian / RHEL)

1. **Install Docker Engine & Compose Plugin**:
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl gnupg git
   
   # Add Docker official GPG key
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   sudo chmod a+r /etc/apt/keyrings/docker.gpg

   # Add repository
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

2. **Clone and Configure**:
   ```bash
   git clone https://github.com/akshat2685/AI_SOC_2.git
   cd AI_SOC_2
   cp .env.example .env
   ```
   Update `.env` with production keys and secure passwords.

3. **Run System as Background Service**:
   ```bash
   sudo docker compose up -d --build
   ```

---

### D. Cloud Deployment (AWS / GCP / Azure & Kubernetes)

#### 1. Cloud Virtual Machine (AWS EC2 / GCP Compute Engine / Azure VM)
- Provision an instance with **Ubuntu 22.04 LTS**, **8 vCPUs**, **32 GB RAM** (e.g., AWS `t3.2xlarge` or GCP `e2-standard-8`).
- Attach an Elastic/Static IP and configure Security Group ingress rules for ports `80`, `443`, and SSH (`22`).
- Execute the **Linux Installation Steps** above.

#### 2. Production Kubernetes Deployment (Helm / K8s Manifests)
ShieldAI includes production Kubernetes manifests located in the `./k8s/` and `./kubernetes/` directories.

1. **Configure Ingress & Secrets**:
   ```bash
   kubectl create namespace shieldai-soc
   kubectl create secret generic shieldai-secrets \
     --from-literal=GEMINI_API_KEY="your_api_key" \
     --from-literal=POSTGRES_PASSWORD="secure_password" \
     -n shieldai-soc
   ```

2. **Apply Kubernetes Manifests**:
   ```bash
   kubectl apply -f ./k8s/ -n shieldai-soc
   ```

3. **Verify Cluster Deployment**:
   ```bash
   kubectl get pods -n shieldai-soc
   ```

---

### E. Integration with SaaS Applications

ShieldAI integrates with enterprise SaaS providers (e.g., Slack, Microsoft Teams, PagerDuty, Okta, Cloudflare, Splunk, CrowdStrike) via webhook routers and REST integration connectors.

1. **Slack / Microsoft Teams Notification Router**:
   - In `.env`, configure notification webhook URLs:
     ```env
     SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
     PAGERDUTY_INTEGRATION_KEY=your_pagerduty_key
     ```

2. **Identity Provider (Okta / Azure AD / Auth0)**:
   - Configure OAuth2 / OIDC environment variables in `backend/app/core/config.py` for SSO integration.

3. **Ingestion Webhooks for External SaaS Logs**:
   - Post external SaaS security telemetry (Cloudflare logs, GitHub audit logs, Google Workspace events) to:
     `POST http://<YOUR_SERVER_IP>/api/v1/telemetry/ingest`

---

## 3. How to Use ShieldAI

### Key Workflows & User Operations

#### 1. Accessing the Web Interfaces
- **SOC Main Dashboard**: Navigate to `http://localhost` (or server IP). View live threat radar, security alerts, and system health metrics.
- **REST API Explorer**: Open `http://localhost:8000/docs` to interact with Swagger API documentation.
- **AI Intelligence Layer API**: Open `http://localhost:8001/docs` to test AI Copilot queries directly.
- **Grafana Monitoring**: Access `http://localhost:3000` (Default credentials: `admin` / `admin_in_production`).
- **Neo4j Attack Graph Explorer**: Access `http://localhost:7474` (Bolt connection: `bolt://localhost:7687`).

---

#### 2. Running Threat & Attack Simulations
ShieldAI includes automated attack simulation scripts to generate synthetic threat events (e.g., SQL Injection, Brute Force, Privilege Escalation, Ransomware Activity):

Run the attack simulator script:
```bash
python simulate_attacks.py
```
This triggers real-time events through Kafka. The worker detects anomalies, writes raw logs to ClickHouse, updates the Neo4j graph, and generates alerts in the dashboard.

---

#### 3. AI Incident Triage & Automated Response
When an alert is flagged:
1. **Automated Graph Reasoning**: Neo4j builds the attack path graph connecting the attacker IP, vulnerable host, and compromised assets.
2. **LLM Summary Generation**: The AI Layer queries Gemini to synthesize raw logs and telemetry into natural-language incident summaries with MITRE ATT&CK mapping.
3. **Automated Playbook Execution**: The SOAR engine executes response actions (e.g., isolating IP, revoking API tokens, triggering Slack alerts).

---

#### 4. Interacting with the AI SOC Copilot
Send natural-language security queries to the AI Copilot endpoint:
```bash
curl -X POST "http://localhost:8001/api/v1/copilot/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "Show all high-severity SSH brute force attempts from the last 2 hours"}'
```

---

#### 5. Codebase & Knowledge Graph Inspection (Graphify)
To explore the internal codebase structure, dependencies, and architecture using Graphify:
- **Launch Interactive Web Graph**: Double-click `graphify-out/graph.html`.
- **View Collapsible Tree Visualizer**: Open `graphify-out/GRAPH_TREE.html`.
- **Query Architecture CLI**:
  ```bash
  graphify query "AutonomousDetectionEngine"
  graphify explain "SOCState"
  ```

---

## 4. Maintenance & Troubleshooting

- **Check Container Logs**:
  ```bash
  docker compose logs -f <container_name>
  # Example:
  docker compose logs -f shieldai-soc
  docker compose logs -f shieldai-worker
  docker compose logs -f shieldai-ai-layer
  ```

- **Restart Services**:
  ```bash
  docker compose restart
  ```

- **Rebuild Containers**:
  ```bash
  docker compose up -d --build --force-recreate
  ```

---
*ShieldAI / EDYSOR Enterprise Documentation v2.0*
