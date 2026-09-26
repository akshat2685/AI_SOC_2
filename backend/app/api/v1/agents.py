"""EDYSOR endpoint agents: enrollment, heartbeat, inventory.

Every agent carries a server-generated `device_id` — agents are never
identified by hostname alone (hostnames change). Effective online/offline
status is computed from heartbeat age at READ time:

- no heartbeat yet      -> unregistered
- heartbeat < 90s ago   -> online
- heartbeat < 5min ago  -> degraded
- heartbeat older       -> offline

Heartbeat auth: require_roles_dual accepts API-key auth as well as JWT,
so agents can heartbeat with a tenant API key.
"""

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.core.auth import current_tenant_id
from app.domain.models import AgentPlatform, AgentStatus, EndpointAgent, RoleEnum
from app.infrastructure.database import get_db

router = APIRouter()
logger = structlog.get_logger(__name__)

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]

ONLINE_THRESHOLD_S = 90
DEGRADED_THRESHOLD_S = 300

# Files the installer snippet may fetch. Served from the packaged sensor/
# directory (see Dockerfile.backend-prod COPY sensor ./sensor).
SENSOR_FILES = {"edysor_sensor.py", "requirements.txt"}


def _sensor_dir() -> Path:
    # <root>/backend/app/api/v1/agents.py -> parents[4] == <root> (dev)
    # and /app/backend/app/api/v1/agents.py -> parents[4] == /app (container).
    return Path(__file__).resolve().parents[4] / "sensor"


def _tenant_id() -> int:
    return current_tenant_id.get() or 1


def _effective_status(agent: EndpointAgent) -> str:
    """Compute live status from heartbeat age. Honest derivation, not a guess."""
    hb = agent.last_heartbeat_at
    if hb is None:
        return AgentStatus.UNREGISTERED.value
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - hb).total_seconds()
    if age < 0:
        return AgentStatus.ONLINE.value  # clock skew: treat as online
    if age <= ONLINE_THRESHOLD_S:
        return AgentStatus.ONLINE.value
    if age <= DEGRADED_THRESHOLD_S:
        return AgentStatus.DEGRADED.value
    return AgentStatus.OFFLINE.value


def _agent_to_dict(agent: EndpointAgent) -> Dict[str, Any]:
    return {
        "id": str(agent.id),
        "tenant_id": agent.tenant_id,
        "device_id": agent.device_id,
        "hostname": agent.hostname,
        "platform": agent.platform.value if agent.platform else None,
        "os_version": agent.os_version,
        "arch": agent.arch,
        "agent_version": agent.agent_version,
        "ip_address": agent.ip_address,
        "status": _effective_status(agent),
        "stored_status": agent.status.value if agent.status else None,
        "last_heartbeat_at": agent.last_heartbeat_at.isoformat() if agent.last_heartbeat_at else None,
        "registered_at": agent.registered_at.isoformat() if agent.registered_at else None,
    }


async def _get_agent(db: AsyncSession, device_id: str, tenant_id: int) -> EndpointAgent:
    result = await db.execute(
        select(EndpointAgent).where(
            EndpointAgent.device_id == device_id, EndpointAgent.tenant_id == tenant_id
        )
    )
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _generate_device_id(db: AsyncSession) -> str:
    """Server-generated unique device identity: 'agt-' + 12 hex chars."""
    for _ in range(5):
        device_id = "agt-" + secrets.token_hex(6)
        result = await db.execute(select(EndpointAgent).where(EndpointAgent.device_id == device_id))
        if not result.scalars().first():
            return device_id
    raise HTTPException(status_code=500, detail="Could not generate a unique device_id; retry.")


@router.post("/register")
async def register_agent(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    """Enroll a device. Returns the server-generated device identity block."""
    tenant_id = _tenant_id()
    hostname = str(data.get("hostname") or "").strip()
    platform = str(data.get("platform") or "").strip().lower()
    if not hostname:
        raise HTTPException(status_code=400, detail="Provide 'hostname'.")
    try:
        platform_enum = AgentPlatform(platform)
    except ValueError:
        valid = [p.value for p in AgentPlatform]
        raise HTTPException(status_code=400, detail=f"Invalid platform. Valid: {valid}")

    device_id = await _generate_device_id(db)
    agent = EndpointAgent(
        tenant_id=tenant_id,
        device_id=device_id,
        hostname=hostname,
        platform=platform_enum,
        os_version=str(data.get("os_version")) if data.get("os_version") else None,
        arch=str(data.get("arch")) if data.get("arch") else None,
        agent_version=str(data.get("agent_version")) if data.get("agent_version") else None,
        ip_address=str(data.get("ip_address")) if data.get("ip_address") else None,
        status=AgentStatus.UNREGISTERED,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    logger.info("agent_registered", device_id=device_id, hostname=hostname, platform=platform)
    return {
        "device_identity": {
            "tenant_id": tenant_id,
            "device_id": device_id,
            "hostname": hostname,
            "platform": platform_enum.value,
            "os_version": agent.os_version,
            "arch": agent.arch,
            "agent_version": agent.agent_version,
            "status": AgentStatus.UNREGISTERED.value,
            "registered_at": agent.registered_at.isoformat() if agent.registered_at else None,
        },
        "note": "Agent starts as 'unregistered' until its first heartbeat.",
    }


# NOTE: literal routes must be registered before /{device_id}.
@router.get("/sensor/download/{filename}")
async def download_sensor(filename: str):
    """Serve the reference sensor installer files.

    Public on purpose: the sensor is inert without a tenant API key
    (registration requires a valid X-API-Key), so the file itself carries
    no privilege. The GitHub repo is private, so installers cannot fetch
    the sensor from raw.githubusercontent.com.
    """
    if filename not in SENSOR_FILES:
        raise HTTPException(status_code=404, detail="unknown sensor file")
    path = _sensor_dir() / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail="sensor file not packaged in this build"
        )
    return FileResponse(path, filename=filename, media_type="text/plain")


@router.get("/stats/summary")
async def agents_summary(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Counts by computed status and by platform (tenant-scoped)."""
    tenant_id = _tenant_id()
    result = await db.execute(select(EndpointAgent).where(EndpointAgent.tenant_id == tenant_id))
    agents = result.scalars().all()
    by_status: Dict[str, int] = {}
    by_platform: Dict[str, int] = {}
    for a in agents:
        st = _effective_status(a)
        by_status[st] = by_status.get(st, 0) + 1
        pl = a.platform.value if a.platform else "unknown"
        by_platform[pl] = by_platform.get(pl, 0) + 1
    return {
        "total": len(agents),
        "by_status": by_status,
        "by_platform": by_platform,
        "status_note": (
            "Status is computed from heartbeat age at read time: online <90s, "
            "degraded <5min, offline beyond that, unregistered before first heartbeat."
        ),
    }


@router.get("")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = _tenant_id()
    result = await db.execute(select(EndpointAgent).where(EndpointAgent.tenant_id == tenant_id))
    return [_agent_to_dict(a) for a in result.scalars().all()]


@router.get("/{device_id}")
async def get_agent(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    agent = await _get_agent(db, device_id, _tenant_id())
    return _agent_to_dict(agent)


@router.post("/{device_id}/heartbeat")
async def agent_heartbeat(
    device_id: str,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Agent heartbeat. Accepts JWT or tenant API key (via require_roles_dual)."""
    agent = await _get_agent(db, device_id, _tenant_id())
    now = datetime.now(timezone.utc)
    agent.last_heartbeat_at = now
    agent.status = AgentStatus.ONLINE
    if data.get("agent_version"):
        agent.agent_version = str(data["agent_version"])
    if data.get("ip_address"):
        agent.ip_address = str(data["ip_address"])
    await db.commit()
    await db.refresh(agent)
    return {
        "device_id": agent.device_id,
        "status": _effective_status(agent),
        "last_heartbeat_at": agent.last_heartbeat_at.isoformat(),
    }


@router.delete("/{device_id}")
async def delete_agent(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    agent = await _get_agent(db, device_id, _tenant_id())
    await db.delete(agent)
    await db.commit()
    logger.info("agent_deleted", device_id=device_id)
    return {"deleted": device_id}
