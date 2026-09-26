"""Sensor command channel.

The sensor polls GET /agents/{device_id}/commands with its tenant API key
(same auth as ingest/heartbeat: require_roles_dual). Pending commands are
returned oldest-first and flipped to "delivered". After executing, the sensor
POSTs /agents/commands/{cmd_id}/ack with {status, result}.

This router is mounted by the parent at prefix "/agents" (same as the
agents router), so the full paths are:
    GET  /api/v1/agents/{device_id}/commands
    POST /api/v1/agents/commands/{cmd_id}/ack
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.core.auth import current_tenant_id
from app.domain.models import EndpointAgent, RoleEnum
from app.infrastructure.database import get_db
from app.response.models import DeviceCommand

logger = structlog.get_logger(__name__)

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]

ACK_STATUSES = ("acked", "failed")


def _tenant_id() -> int:
    return current_tenant_id.get() or 1


def _command_to_dict(cmd: DeviceCommand) -> Dict[str, Any]:
    return {
        "id": cmd.id,
        "device_id": cmd.device_id,
        "action": cmd.action,
        "params": cmd.params or {},
        "status": cmd.status,
        "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
    }


class AckBody(BaseModel):
    status: str
    result: Dict[str, Any] = {}


@router.get("/{device_id}/commands")
async def poll_commands(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Sensor long-poll endpoint: fetch pending commands for this device.

    Pending commands are returned and marked "delivered". A command that was
    delivered but never acked is re-offered on the next poll.
    """
    tenant_id = _tenant_id()
    agent = (
        (await db.execute(
            select(EndpointAgent).where(
                EndpointAgent.device_id == device_id,
                EndpointAgent.tenant_id == tenant_id,
            )
        ))
        .scalars()
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    stmt = (
        select(DeviceCommand)
        .where(
            DeviceCommand.tenant_id == tenant_id,
            DeviceCommand.device_id == device_id,
            DeviceCommand.status.in_(("pending", "delivered")),
        )
        .order_by(DeviceCommand.created_at.asc())
        .limit(50)
    )
    commands: List[DeviceCommand] = list((await db.execute(stmt)).scalars().all())
    for cmd in commands:
        if cmd.status == "pending":
            cmd.status = "delivered"
    if commands:
        await db.commit()
        logger.info("commands_delivered", device_id=device_id, count=len(commands))
    return {"device_id": device_id, "commands": [_command_to_dict(c) for c in commands]}


@router.post("/commands/{cmd_id}/ack")
async def ack_command(
    cmd_id: int,
    body: AckBody,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Sensor ack: report execution outcome for one command."""
    if body.status not in ACK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {ACK_STATUSES}",
        )
    tenant_id = _tenant_id()
    cmd = (
        (await db.execute(
            select(DeviceCommand).where(
                DeviceCommand.id == cmd_id,
                DeviceCommand.tenant_id == tenant_id,
            )
        ))
        .scalars()
        .first()
    )
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.status in ("acked", "failed"):
        raise HTTPException(status_code=409, detail=f"Command already {cmd.status}")
    cmd.status = body.status
    cmd.acked_at = datetime.now(timezone.utc)
    cmd.result = body.result or {}
    await db.commit()
    logger.info(
        "command_acked",
        command_id=cmd.id,
        device_id=cmd.device_id,
        action=cmd.action,
        status=body.status,
    )
    return {"id": cmd.id, "status": cmd.status}
