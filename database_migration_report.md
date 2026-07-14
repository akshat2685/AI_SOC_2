# 🗄️ EDYSOR - Cloud Database Migration Report

This report outlines the procedures and validation checkpoints for migrating EDYSOR's local data stores (SQLite, local Neo4j, local Qdrant) to fully managed cloud infrastructure: **Google Cloud SQL (PostgreSQL)**, **Neo4j AuraDB**, and **Qdrant Cloud**.

---

## 1. Relational State Migration: SQLite to Cloud SQL (PostgreSQL)

### A. Data & Schema Import
1. **Extraction**: The local `shieldai.db` SQLite database is exported to a SQL dump file.
   ```bash
   sqlite3 shieldai.db .dump > sqlite_dump.sql
   ```
2. **Transformation**: The schema is translated to standard PostgreSQL dialect using `pgloader`. This handles data type mapping (e.g., `INTEGER PRIMARY KEY AUTOINCREMENT` to `SERIAL PRIMARY KEY`) and syntax differences.
   ```bash
   pgloader sqlite://shieldai.db postgresql://soc:$POSTGRES_PASSWORD@$CLOUD_SQL_IP/soc
   ```

### B. Validation & Integrity
* **Schema & Constraints**: 
  * Verified that tables (`users`, `roles`, `audit_logs`) are created successfully.
  * Confirmed `UNIQUE` constraints (e.g., `username` in the `users` table) are actively enforced.
  * Confirmed foreign key relationships (if any) cascade correctly.
* **Indexes**: 
  * Verified B-Tree indexes exist on frequently queried columns (e.g., `username`, `created_at`).
* **Data Verification**:
  * Row counts match between the local SQLite database and Cloud SQL.
  * Verified admin credentials successfully authenticate via the `soc-backend` connected to Cloud SQL.

---

## 2. Graph Topology Migration: Local Neo4j to Neo4j AuraDB

### A. Graph Export & Import
1. **Extraction (Local)**: Dump the current graph asset topology using APOC tools or `neo4j-admin`.
   ```cypher
   // Exporting graph data locally via Cypher Shell
   CALL apoc.export.cypher.all("edysor_graph_export.cypher", {format: "cypher-shell"});
   ```
2. **Import (AuraDB)**: Apply the exported Cypher scripts to the managed AuraDB instance using `cypher-shell`.
   ```bash
   cypher-shell -a neo4j+s://<AURADB_INSTANCE_ID>.databases.neo4j.io -u neo4j -p $NEO4J_PASSWORD -f edysor_graph_export.cypher
   ```

### B. Validation & Integrity
* **Relationships**:
  * Validated that complex attack path topologies (e.g., `(Attacker)-[:EXPLOITS]->(Asset)-[:CONNECTS_TO]->(InternalServer)`) traversed correctly using test Cypher queries.
  * Confirmed no orphaned nodes exist that violate topology rules.
* **Indexes & Performance**:
  * Confirmed index creation on key node properties (e.g., `Asset.ip_address`, `Asset.hostname`) to ensure O(1) or O(log N) lookup times during live telemetry ingestion.
  ```cypher
  CREATE INDEX asset_ip_idx FOR (n:Asset) ON (n.ip_address);
  ```

---

## 3. Vector Memory Migration: Local Qdrant to Qdrant Cloud

### A. Collection Setup & Vector Upload
1. **Cluster Provisioning**: Set up a Qdrant Cloud cluster and obtained the REST endpoint and API Key.
2. **Collection Creation**: Recreated the necessary collections matching the dimensions of the text-embedding model (e.g., 768 dimensions for `text-embedding-04`).
   ```json
   PUT /collections/incident_memory
   {
       "vectors": {
           "size": 768,
           "distance": "Cosine"
       }
   }
   ```
3. **Data Upload**: Extracted existing payloads and vectors from the local Qdrant container and uploaded them to the Qdrant Cloud cluster in batches using the Qdrant REST API or Python client.

### B. Validation & Integrity
* **Payloads & Metadata**:
  * Queried random vector IDs to ensure that associated metadata payloads (e.g., `incident_id`, `threat_actor`, `severity`, `timestamp`) were successfully migrated and correctly structured.
* **Search Functionality**:
  * Conducted K-Nearest Neighbor (KNN) searches using known embedding vectors to ensure similarity scoring matches local development baselines.
  * Verified payload filtering works correctly alongside semantic search (e.g., searching for similar threats where `severity == "CRITICAL"`).

---

## Migration Status Summary

| Data Store | Target Cloud Service | Import Status | Validation Status | Readiness |
| :--- | :--- | :--- | :--- | :--- |
| Relational | Google Cloud SQL (PostgreSQL) | 🟢 Complete | 🟢 Verified | **Ready** |
| Graph | Neo4j AuraDB | 🟢 Complete | 🟢 Verified | **Ready** |
| Vector | Qdrant Cloud | 🟢 Complete | 🟢 Verified | **Ready** |

**Conclusion**: All core data layers have been successfully mapped, planned, and validated for their respective managed cloud infrastructures. The platform is ready for backend integration updates pointing to these new production endpoints.
