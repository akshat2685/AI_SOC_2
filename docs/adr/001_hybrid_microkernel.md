# ADR 001: Hybrid Microkernel Architecture

## Context
EDYSOR-X originated as a Node.js prototype with an in-memory database (`server.js`). As the requirements evolved into an AI-Native Autonomous SOC, complex Python-based AI workflows (LangGraph, Neo4j, Qdrant) were introduced via the Intelligence Engine. 

We face a choice:
1. Rewrite the entire frontend and backend completely in Python (huge effort, pauses feature work).
2. Rewrite the AI logic in Node.js (poor AI ecosystem support).
3. Connect the two ecosystems.

## Decision
We will adopt a **Hybrid Microkernel Architecture**.
- The **Node.js layer** acts as the API Gateway, UI server, WebSocket handler, and thin proxy.
- The **Python layer (FastAPI)** acts as the core Intelligence Engine, running agents, LLM integrations, and heavy ML/RAG pipelines.
- Communication between them happens via HTTP (proxied routes) and Kafka (event streaming).

## Consequences
- **Positive:** Leverages existing React frontend without rewrite.
- **Positive:** Python remains the best language for AI/ML/Data tasks.
- **Positive:** Allows for incremental decomposition of the `server.js` monolith.
- **Negative:** Dual stack increases operational complexity.
- **Negative:** Adds a network hop for proxied API requests.

## Alternatives Considered
- **Full Rewrite in FastAPI:** Rejected. Too time-consuming. We need to deliver Phase 2-28 features rapidly while maintaining existing UI functionality.
- **gRPC instead of HTTP:** Considered. May adopt in Phase 21 (Performance) if HTTP overhead becomes a bottleneck, but HTTP is simpler for immediate integration.
