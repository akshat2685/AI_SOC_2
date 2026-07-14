# ShieldAI SOC Platform: Cloud Architecture
**Milestone 12 - Documentation & Handover**

## 1. High-Level Architecture
The ShieldAI SOC Platform is designed as a highly scalable, serverless microservices architecture built on Google Cloud Platform (GCP). It leverages a tri-database strategy to handle relational state, graph topology, and high-dimensional vector memory.

## 2. Core Components

### 2.1 Compute Layer
*   **Google Cloud Run (Gen 2):** Hosts the Express.js Node application. It provides auto-scaling (scale-to-zero), HTTP/2 support, and native WebSocket streaming.

### 2.2 Data Persistence Layer
*   **Neo4j AuraDB (Graph):** Stores the cybersecurity knowledge graph, mapping the relationships between hosts, IPs, users, and threat actors for blast-radius calculation.
*   **Qdrant Cloud (Vector RAG):** Stores vector embeddings of historical incidents, SOC playbooks, and threat intelligence reports for semantic search and retrieval.
*   **Relational DB (Cloud SQL / SQLite):** Manages standard application state, user accounts, and structured incident metadata.

### 2.3 AI & Analytics Layer
*   **Google Gemini API:** Serves as the cognitive engine for the platform. It handles:
    *   Zero-shot routing of analytical tasks to specialized sub-agents.
    *   Synthesizing context from Neo4j and Qdrant into actionable human-readable reports.

## 3. Request Flow (Example: GraphRAG Query)
1.  **Ingress:** User submits a natural language query via the frontend UI.
2.  **API Gateway:** Request hits Cloud Run; Express middleware applies Rate Limiting and Helmet security headers.
3.  **Vector Retrieval:** Backend queries Qdrant to find semantically similar historical playbooks.
4.  **Graph Traversal:** Backend queries Neo4j via Cypher to extract the specific asset topology related to the query.
5.  **AI Synthesis:** The Express server constructs a prompt combining the Vector Context + Graph Context + User Query and sends it to the Gemini API.
6.  **Response:** Gemini returns the synthesized analysis, which is streamed back to the client.

## 4. Security Architecture
*   **Identity:** Managed via JWT and OAuth 2.0.
*   **Secrets:** Google Cloud Secret Manager injects credentials at runtime.
*   **Network:** All inter-service communication (Cloud Run to Neo4j/Qdrant) is TLS encrypted.
