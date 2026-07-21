# Phase 10: Multi-Tenant Architecture Design (Revised for Security)

## 1. Overview
This document outlines the architecture for introducing multi-tenancy to the AI SOC platform. The goal is to support multiple organizations (tenants) within a single deployment, ensuring strict data isolation, role-based access control (RBAC), and tenant-specific management of assets and incidents.

## 2. Tenant Isolation Strategy
We will use a **Shared Database, Shared Schema** approach with **Native PostgreSQL Row-Level Security (RLS)**. 
Data isolation will be enforced at the database level:
- RLS policies must be enabled for all tenant-specific entities (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`).
- Application sessions must set a session variable before executing queries (e.g., `SET LOCAL rls.tenant_id = :id`).
- This guarantees isolation even if application-level filtering logic fails or is bypassed.

## 3. Data Model Changes

### 3.1 New Models
- **Tenant**
  - `id`: Primary Key
  - `name`: String, unique
  - `created_at`: DateTime

- **User**
  - `id`: Primary Key
  - `tenant_id`: ForeignKey(Tenant.id) - nullable only for global admins
  - `email`: String, unique
  - `hashed_password`: String
  - `role`: Enum (GLOBAL_ADMIN, TENANT_ADMIN, TENANT_ANALYST, TENANT_VIEWER)
  - `created_at`: DateTime

- **Asset**
  - `id`: Primary Key
  - `tenant_id`: ForeignKey(Tenant.id) - **NOT NULL**
  - `hostname`: String
  - `ip_address`: String
  - `asset_type`: String
  - `criticality`: Enum (LOW, MEDIUM, HIGH, CRITICAL)

### 3.2 Updates to Existing Models
- **Incident**
  - Add `tenant_id`: ForeignKey(Tenant.id) - **NOT NULL**
- **Alert**
  - Add `tenant_id`: ForeignKey(Tenant.id) - **NOT NULL**

## 4. Role-Based Access Control (RBAC) & Protections
Access control will be managed through a combination of `tenant_id` validation and role-based permissions:

- **GLOBAL_ADMIN**: Can manage all tenants, users, and view cross-tenant data. (tenant_id = null). **Validation requirement: Global Admins cannot create tenant-specific records (Assets, Incidents, Alerts) with a null `tenant_id`. They must specify a target tenant.**
- **TENANT_ADMIN**: Can manage users, assets, and configure settings *within their specific tenant*.
- **TENANT_ANALYST**: Can view and manage incidents, alerts, and assets *within their specific tenant*.
- **TENANT_VIEWER**: Read-only access to incidents and dashboards *within their specific tenant*.

## 5. Implementation Steps for Coder

1.  **Database Models (`backend/app/domain/models.py`)**:
    - Add `Tenant`, `User`, and `Asset` models.
    - Add `tenant_id` to `Incident` and `Alert`.
    - Setup relationships.

2.  **Native PostgreSQL RLS**:
    - Provide raw SQL scripts or Alembic hooks to execute `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`.
    - Define RLS policies based on `current_setting('rls.tenant_id')`.
    - Modify the database session setup (`backend/app/infrastructure/database.py`) or repository to inject `SET LOCAL rls.tenant_id = :id` at the start of a transaction for tenant users.

3.  **Repository Security (`backend/app/infrastructure/repositories.py`)**:
    - **Cross-Tenant Leakage Protection**: Explicitly modify `BaseRepository.update` (or model-specific update logic) to strip/remove the `tenant_id` field from the update payload. This prevents a user from moving a record to another tenant by injecting a malicious `tenant_id`.

4.  **Global Role Validations**:
    - In the service or API layer, explicitly validate that `GLOBAL_ADMIN` users supply a valid `tenant_id` when creating tenant-specific resources (like Assets, Incidents), preventing the creation of orphan or inaccessible records.

5.  **Alembic Migrations**:
    - Generate and apply Alembic migrations for the new schema changes, ensuring RLS policies are included.
