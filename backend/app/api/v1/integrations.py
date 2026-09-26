"""EDYSOR integrations platform: connector catalog, tenant integrations,
health, and onboarding wizard state.

Security rules (non-negotiable):
- Every row is tenant-scoped via current_tenant_id.
- `config` stores only non-secret fields. Any key that looks like a
  credential (password / secret / token / api key) is stripped before
  persistence; only `has_credentials=True` is recorded.
- POST /integrations/{id}/test is CONFIG VALIDATION ONLY. It checks that
  the required non-secret fields for the connector are present. It does
  NOT open a live connection to the vendor and must never claim to.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.core.auth import current_tenant_id
from app.domain.models import (
    Integration,
    IntegrationCategory,
    IntegrationStatus,
    RoleEnum,
)
from app.infrastructure.database import get_db

router = APIRouter()
logger = structlog.get_logger(__name__)

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]

# ---------------------------------------------------------------------------
# Connector catalog (static)
# ---------------------------------------------------------------------------

CONNECTOR_CATALOG: List[Dict[str, Any]] = [
    {
        "key": "windows-agent",
        "name": "EDYSOR Windows Agent",
        "category": "endpoint",
        "connection_method": "agent_installer",
        "capabilities": ["process telemetry", "network connections", "logon events", "isolate endpoint", "terminate process"],
        "required_permissions": ["install service", "read process list", "read network state"],
        "data_collected": ["processes", "network connections", "logons", "file activity", "persistence indicators"],
        "required_config_fields": [],
    },
    {
        "key": "macos-agent",
        "name": "EDYSOR macOS Agent",
        "category": "endpoint",
        "connection_method": "agent_installer",
        "capabilities": ["process telemetry", "network connections", "system events"],
        "required_permissions": ["System Monitoring", "Process Monitoring", "Network Visibility"],
        "data_collected": ["processes", "network connections", "system events"],
        "required_config_fields": [],
    },
    {
        "key": "linux-agent",
        "name": "EDYSOR Linux Agent",
        "category": "endpoint",
        "connection_method": "agent_installer",
        "capabilities": ["process telemetry", "network connections", "audit events", "isolate endpoint"],
        "required_permissions": ["install daemon", "read /proc", "auditd or equivalent"],
        "data_collected": ["processes", "network connections", "auth events", "file activity"],
        "required_config_fields": [],
    },
    {
        "key": "splunk",
        "name": "Splunk",
        "category": "siem",
        "connection_method": "hec_api",
        "capabilities": ["search", "ingest alerts", "event streaming"],
        "required_permissions": ["HEC token", "search scope"],
        "data_collected": ["alerts", "search results", "notable events"],
        "required_config_fields": ["hec_url"],
    },
    {
        "key": "sentinel",
        "name": "Microsoft Sentinel",
        "category": "siem",
        "connection_method": "rest_api",
        "capabilities": ["incident sync", "alert ingestion", "hunting queries"],
        "required_permissions": ["Log Analytics Reader", "Sentinel Responder (optional)"],
        "data_collected": ["incidents", "alerts", "entities"],
        "required_config_fields": ["workspace_id"],
    },
    {
        "key": "crowdstrike",
        "name": "CrowdStrike Falcon",
        "category": "edr",
        "connection_method": "oauth_api",
        "capabilities": ["detections", "host search", "contain host", "threat intel"],
        "required_permissions": ["Falcon API client (detections:read, hosts:read)"],
        "data_collected": ["detections", "host inventory", "process timelines"],
        "required_config_fields": ["base_url", "client_id"],
    },
    {
        "key": "defender",
        "name": "Microsoft Defender for Endpoint",
        "category": "edr",
        "connection_method": "oauth_api",
        "capabilities": ["alerts", "machine actions", "threat intel"],
        "required_permissions": ["Entra app: Alert.Read.All, Machine.Read.All"],
        "data_collected": ["alerts", "devices", "vulnerabilities"],
        "required_config_fields": ["tenant_id"],
    },
    {
        "key": "paloalto",
        "name": "Palo Alto Networks",
        "category": "firewall",
        "connection_method": "api_or_syslog",
        "capabilities": ["traffic logs", "threat logs", "block ip/url"],
        "required_permissions": ["API key with log access", "syslog receiver"],
        "data_collected": ["allowed/blocked traffic", "threat events", "url filtering"],
        "required_config_fields": ["host"],
    },
    {
        "key": "fortinet",
        "name": "Fortinet FortiGate",
        "category": "firewall",
        "connection_method": "api_or_syslog",
        "capabilities": ["traffic logs", "ips events", "block ip"],
        "required_permissions": ["API token", "syslog receiver"],
        "data_collected": ["traffic logs", "ips signatures", "vpn events"],
        "required_config_fields": ["host"],
    },
    {
        "key": "okta",
        "name": "Okta",
        "category": "iam",
        "connection_method": "oauth_api",
        "capabilities": ["auth events", "user inventory", "suspend user"],
        "required_permissions": ["Okta API token (read users, read logs)"],
        "data_collected": ["logins", "mfa events", "user lifecycle"],
        "required_config_fields": ["domain"],
    },
    {
        "key": "entra",
        "name": "Microsoft Entra ID",
        "category": "iam",
        "connection_method": "oauth_api",
        "capabilities": ["sign-in logs", "user inventory", "risk detections"],
        "required_permissions": ["Entra app: AuditLog.Read.All, User.Read.All"],
        "data_collected": ["sign-ins", "mfa events", "risky users"],
        "required_config_fields": ["tenant_id"],
    },
    {
        "key": "aws",
        "name": "Amazon Web Services",
        "category": "cloud",
        "connection_method": "iam_role",
        "capabilities": ["cloudtrail events", "guardduty findings", "config changes"],
        "required_permissions": ["IAM role: CloudTrail read, GuardDuty read"],
        "data_collected": ["api activity", "findings", "resource changes"],
        "required_config_fields": ["region"],
    },
    {
        "key": "azure",
        "name": "Microsoft Azure",
        "category": "cloud",
        "connection_method": "service_principal",
        "capabilities": ["activity log", "defender for cloud alerts"],
        "required_permissions": ["Service principal: Reader + Security Reader"],
        "data_collected": ["activity logs", "security alerts", "resource inventory"],
        "required_config_fields": ["subscription_id"],
    },
    {
        "key": "gcp",
        "name": "Google Cloud Platform",
        "category": "cloud",
        "connection_method": "service_account",
        "capabilities": ["audit logs", "scc findings"],
        "required_permissions": ["Service account: logging.viewer, securitycenter.findingsViewer"],
        "data_collected": ["audit logs", "findings", "asset inventory"],
        "required_config_fields": ["project_id"],
    },
    {
        "key": "misp",
        "name": "MISP",
        "category": "threat_intel",
        "connection_method": "api",
        "capabilities": ["indicator lookup", "event sync", "sighting feed"],
        "required_permissions": ["MISP auth key (read)"],
        "data_collected": ["indicators", "attributes", "sightings"],
        "required_config_fields": ["url"],
    },
    {
        "key": "webhook",
        "name": "Generic Webhook",
        "category": "custom",
        "connection_method": "inbound_webhook",
        "capabilities": ["receive events"],
        "required_permissions": ["shared signing secret"],
        "data_collected": ["custom event payloads"],
        "required_config_fields": ["url"],
    },
    {
        "key": "syslog",
        "name": "Syslog Source",
        "category": "custom",
        "connection_method": "syslog",
        "capabilities": ["receive syslog stream"],
        "required_permissions": ["network reachability to collector"],
        "data_collected": ["syslog messages"],
        "required_config_fields": ["host", "port"],
    },
    {
        "key": "custom-api",
        "name": "Custom API Poller",
        "category": "custom",
        "connection_method": "rest_poll",
        "capabilities": ["poll rest endpoints", "field mapping to canonical schema"],
        "required_permissions": ["API credentials for the source system"],
        "data_collected": ["custom events"],
        "required_config_fields": ["base_url"],
    },
]

CATALOG_BY_KEY = {c["key"]: c for c in CONNECTOR_CATALOG}

# Any config key containing one of these fragments (case-insensitive) is
# treated as a credential and stripped before persistence.
SECRET_FRAGMENTS = ("password", "secret", "token", "api_key", "apikey", "private_key", "client_secret")


def _scrub_config(config: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """Return (scrubbed_config, had_credentials). Never persists raw secrets."""
    scrubbed: Dict[str, Any] = {}
    had_credentials = False
    for k, v in (config or {}).items():
        if any(frag in str(k).lower() for frag in SECRET_FRAGMENTS):
            had_credentials = True
            continue
        scrubbed[k] = v
    return scrubbed, had_credentials


def _tenant_id() -> int:
    return current_tenant_id.get() or 1


def _integration_to_dict(i: Integration) -> Dict[str, Any]:
    return {
        "id": str(i.id),
        "name": i.name,
        "category": i.category.value if i.category else None,
        "connector_key": i.connector_key,
        "status": i.status.value if i.status else None,
        "config": i.config or {},
        "has_credentials": bool(i.has_credentials),
        "events_received": i.events_received or 0,
        "events_rejected": i.events_rejected or 0,
        "error_count": i.error_count or 0,
        "last_error": i.last_error,
        "last_seen_at": i.last_seen_at.isoformat() if i.last_seen_at else None,
        "last_event_at": i.last_event_at.isoformat() if i.last_event_at else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    }


async def _get_integration(db: AsyncSession, integration_id: UUID, tenant_id: int) -> Integration:
    result = await db.execute(
        select(Integration).where(Integration.id == integration_id, Integration.tenant_id == tenant_id)
    )
    integration = result.scalars().first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@router.get("/catalog")
async def get_catalog(_auth=Depends(require_roles_dual(READ_ROLES))):
    """Static catalog of supported connectors. No tenant data involved."""
    return {"connectors": CONNECTOR_CATALOG, "count": len(CONNECTOR_CATALOG)}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = _tenant_id()
    result = await db.execute(select(Integration).where(Integration.tenant_id == tenant_id))
    return [_integration_to_dict(i) for i in result.scalars().all()]


@router.post("")
async def create_integration(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    tenant_id = _tenant_id()
    name = str(data.get("name") or "").strip()
    category = str(data.get("category") or "").strip()
    connector_key = str(data.get("connector_key") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provide 'name'.")
    if not category:
        raise HTTPException(status_code=400, detail="Provide 'category'.")
    try:
        category_enum = IntegrationCategory(category)
    except ValueError:
        valid = [c.value for c in IntegrationCategory]
        raise HTTPException(status_code=400, detail=f"Invalid category. Valid: {valid}")
    if not connector_key:
        raise HTTPException(status_code=400, detail="Provide 'connector_key'.")

    config, had_credentials = _scrub_config(data.get("config") or {})
    if had_credentials:
        logger.info("integration_credentials_scrubbed", connector_key=connector_key)

    integration = Integration(
        tenant_id=tenant_id,
        name=name,
        category=category_enum,
        connector_key=connector_key,
        status=IntegrationStatus.DISCONNECTED,
        config=config,
        has_credentials=had_credentials,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return _integration_to_dict(integration)


@router.get("/{integration_id}")
async def get_integration(
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    integration = await _get_integration(db, integration_id, _tenant_id())
    return _integration_to_dict(integration)


@router.put("/{integration_id}")
async def update_integration(
    integration_id: UUID,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    integration = await _get_integration(db, integration_id, _tenant_id())
    if "name" in data and data["name"]:
        integration.name = str(data["name"]).strip()
    if "category" in data and data["category"]:
        try:
            integration.category = IntegrationCategory(str(data["category"]).strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid category.")
    if "connector_key" in data and data["connector_key"]:
        integration.connector_key = str(data["connector_key"]).strip()
    if "config" in data:
        config, had_credentials = _scrub_config(data.get("config") or {})
        integration.config = config
        if had_credentials:
            integration.has_credentials = True
    if "status" in data and data["status"]:
        try:
            integration.status = IntegrationStatus(str(data["status"]).strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status.")
    await db.commit()
    await db.refresh(integration)
    return _integration_to_dict(integration)


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    integration = await _get_integration(db, integration_id, _tenant_id())
    await db.delete(integration)
    await db.commit()
    return {"deleted": str(integration_id)}


# ---------------------------------------------------------------------------
# Test connection (config validation only — never a live vendor connection)
# ---------------------------------------------------------------------------

@router.post("/{integration_id}/test")
async def test_integration(
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    """Validate the integration's stored configuration.

    This checks that the required non-secret config fields for the
    connector are present. It does NOT contact the vendor — no live
    connection is established or claimed.
    """
    integration = await _get_integration(db, integration_id, _tenant_id())
    catalog_entry = CATALOG_BY_KEY.get(integration.connector_key, {})
    required = catalog_entry.get("required_config_fields", [])
    config = integration.config or {}

    checks: List[Dict[str, Any]] = []
    ok = True
    for field in required:
        present = bool(config.get(field))
        checks.append({
            "name": f"config field '{field}' present",
            "passed": present,
            "detail": "present" if present else "missing — set it in the integration config",
        })
        if not present:
            ok = False
    checks.append({
        "name": "connector recognized",
        "passed": integration.connector_key in CATALOG_BY_KEY,
        "detail": "known connector" if integration.connector_key in CATALOG_BY_KEY else "custom/unknown connector — field checks skipped",
    })
    if not required:
        checks.append({
            "name": "required fields",
            "passed": True,
            "detail": "this connector declares no required non-secret config fields",
        })

    return {
        "ok": ok,
        "integration_id": str(integration.id),
        "connector_key": integration.connector_key,
        "checks": checks,
        "note": (
            "Config validation only — this endpoint checks stored configuration "
            "fields and does NOT establish a live connection to the vendor."
        ),
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/{integration_id}/health")
async def integration_health(
    integration_id: UUID,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Integration health: status, counters, last error, data latency."""
    integration = await _get_integration(db, integration_id, _tenant_id())
    now = datetime.now(timezone.utc)
    latency: Optional[float] = None
    if integration.last_event_at:
        last_event = integration.last_event_at
        if last_event.tzinfo is None:
            last_event = last_event.replace(tzinfo=timezone.utc)
        latency = (now - last_event).total_seconds()
    return {
        "integration_id": str(integration.id),
        "name": integration.name,
        "status": integration.status.value if integration.status else None,
        "last_seen_at": integration.last_seen_at.isoformat() if integration.last_seen_at else None,
        "last_event_at": integration.last_event_at.isoformat() if integration.last_event_at else None,
        "data_latency_seconds": latency,
        "events_received": integration.events_received or 0,
        "events_rejected": integration.events_rejected or 0,
        "error_count": integration.error_count or 0,
        "last_error": integration.last_error,
    }

