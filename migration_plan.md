# 🗺️ SQLite to Google Cloud SQL (PostgreSQL) Migration Plan

This plan establishes the operational steps required to transition **EDYSOR**'s relational state from a local SQLite3 file database (`shieldai.db`) to a production-ready, fully managed **Google Cloud SQL (PostgreSQL)** instance. 

This migration ensures higher concurrency, durable automated backups, point-in-time recovery, high availability, and strict IAM-based access control.

---

## 1. Prerequisites & Target Architecture
* **Source Database**: Local SQLite3 (`shieldai.db`) containing user tables, roles, and schema metadata.
* **Target Database**: Google Cloud SQL for PostgreSQL (V16), configured with:
  - Private IP networking (within the Shared VPC of the SOC environment)
  - IAM database authentication enabled
  - Automatic daily backups and transactional logs
* **Orchestration Layer Connection**: The Node.js Express backend (`server.js`) will be modified to support a dual-engine database driver pool, reading `DB_TYPE=postgres` from environment configurations to establish native connection pooling via the PostgreSQL client.

---

## 2. Step-by-Step Migration Execution

### Phase A: Setup & Provisioning
1. **Provision Google Cloud SQL PostgreSQL**:
   - Create a Cloud SQL instance via the GCP Console, gcloud CLI, or Terraform:
     ```bash
     gcloud sql instances create edysor-postgres \
         --database-version=POSTGRES_16 \
         --tier=db-custom-2-7680 \
         --region=us-central1 \
         --root-password="YourSecurePasswordHere"
     ```
   - Create the target database:
     ```bash
     gcloud sql databases create soc --instance=edysor-postgres
     ```
2. **Configure Networking & Access Control**:
   - Establish Private Service Access (PSA) to allow direct access from Cloud Run or Google Kubernetes Engine (GKE) via Private IP.
   - For remote administrator CLI tooling or local debugging, configure authorized networks or utilize the secure **Cloud SQL Auth Proxy**:
     ```bash
     ./cloud-sql-proxy --private-ip <YOUR_INSTANCE_CONNECTION_NAME>
     ```

### Phase B: Code Updates & Dependency Integration
1. **Install PostgreSQL Node Driver**:
   Add the native `pg` package and its TypeScript definitions to the workspace:
   ```bash
   npm install pg
   npm install --save-dev @types/pg
   ```
2. **Refactor Database Module (`db.js` / `server.js`)**:
   Implement a database abstraction module that checks `DB_TYPE` and exports unified query interfaces (`query`, `get`, `run` wrapper compatibility layers) to support both engine backends seamlessly:
   ```javascript
   import pg from 'pg';
   import sqlite3 from 'sqlite3';

   let dbClient;

   if (process.env.DB_TYPE === 'postgres') {
     const pool = new pg.Pool({
       connectionString: process.env.POSTGRES_URL || `postgresql://${process.env.POSTGRES_USER}:${process.env.POSTGRES_PASSWORD}@${process.env.POSTGRES_HOST}:${process.env.POSTGRES_PORT}/${process.env.POSTGRES_DB}`
     });
     
     dbClient = {
       run: (sql, params) => pool.query(sql, params),
       get: async (sql, params) => {
         const res = await pool.query(sql, params);
         return res.rows[0];
       },
       all: async (sql, params) => {
         const res = await pool.query(sql, params);
         return res.rows;
       }
     };
     console.log('[DB] Configured for Google Cloud SQL (PostgreSQL).');
   } else {
     // SQLite fallback
     const localDb = new sqlite3.Database('./shieldai.db');
     // ...promisify SQLite methods to match dbClient interface
   }
   ```
3. **Align SQL Dialects**:
   - Replace SQLite-specific syntax with standard ANSI SQL.
   - For example, convert the `INSERT OR IGNORE` SQLite syntax used in `server.js` line 341 to a standard PostgreSQL `ON CONFLICT DO NOTHING` statement:
     ```sql
     -- SQLite (Old)
     INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin', 'admin');

     -- PostgreSQL (New)
     INSERT INTO users (username, password, role) VALUES ('admin', 'admin', 'admin') 
     ON CONFLICT (username) DO NOTHING;
     ```

### Phase C: Data Schema & Storage Migration
1. **Extract Schema & Seed Rows from SQLite**:
   Export the existing local database structure and data:
   ```bash
   sqlite3 shieldai.db .dump > sqlite_dump.sql
   ```
2. **Convert & Format to PostgreSQL Dialect**:
   Clean up SQLite specific markers in `sqlite_dump.sql` (e.g. `PRAGMA`, transaction tags, non-Postgres text fields) or use an open-source converter tool like `pgloader`:
   ```pgloader
   load database
        from sqlite://./shieldai.db
        into postgresql://soc:password@localhost:5432/soc

    with include drop, create tables, create indexes, reset sequences;
   ```
3. **Execute Import**:
   Connect to Cloud SQL (via Proxy) and pipe the converted schemas to populate the managed database tables:
   ```bash
   psql -h 127.0.0.1 -U soc -d soc -f postgres_ready_dump.sql
   ```

### Phase D: Environment Variables Updates
Configure the container runtime (e.g. Cloud Run, GKE) with the following environment variables:
```env
DB_TYPE=postgres
POSTGRES_HOST=127.0.0.1 (or Private IP of Cloud SQL Instance)
POSTGRES_PORT=5432
POSTGRES_DB=soc
POSTGRES_USER=soc
POSTGRES_PASSWORD=secure_password_managed_in_gcp_secret_manager
POSTGRES_URL=postgresql://soc:secure_password@127.0.0.1:5432/soc
```

### Phase E: Verification & Validation Testing
1. **Heuristics Build**: Compile the applet locally (`npm run build`) to ensure all import syntax is verified.
2. **Connection Handshake Verification**: Inspect deployment console startup streams for `[DB] Configured for Google Cloud SQL` declarations.
3. **Integrity checks**: Perform simulated logins on the analyst console to verify that authentication reads/writes execute successfully against the PostgreSQL state database.
4. **Active Fallback verification**: Temporarily unset `DB_TYPE` to ensure the platform falls back securely to internal SQLite states without crashes.

---

## 3. Rollback & Contingency Plan
* **Trigger Conditions**: If PostgreSQL handshake failures occur on live environments, or if query latency violates SLO bounds (>150ms).
* **Rollback Protocol**:
  1. Revert container configuration variables: Set `DB_TYPE=sqlite` or delete the environment variable.
  2. The application will instantly fall back to local SQLite state storage during troubleshooting cycles.
  3. Analyze PostgreSQL query performance logs and check VPC peering routing metrics.
