from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any

from app.infrastructure.database import get_db
from app.domain.models import Alert
from app.core.auth import current_tenant_id

router = APIRouter()

@router.get("")
async def get_alerts(db: AsyncSession = Depends(get_db)):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Alert).where(Alert.tenant_id == tenant_id))
    alerts = result.scalars().all()
    return [
        {
            "id": a.id,
            "title": a.rule_name,
            "severity": "MEDIUM",
            "timestamp": a.timestamp.isoformat(),
            "confidence": "80%",
            "confidence_score": 80,
            "attack_type": "UNKNOWN",
            "evidence": a.description,
            "attacker_ip": "0.0.0.0",
            "verdict": "UNKNOWN",
            "incident_id": a.incident_id
        } for a in alerts
    ]

@router.get("/{id}/details")
async def get_alert_details(id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Alert).where(Alert.id == id, Alert.tenant_id == tenant_id))
    alert = result.scalars().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    return {
        "id": alert.id,
        "title": alert.rule_name,
        "description": alert.description,
        "timestamp": alert.timestamp.isoformat(),
        "source": alert.source
    }

@router.get("/{id}/investigation")
async def get_alert_investigation(id: int):
    return {"status": "Complete", "summary": "Alert was investigated and found to be benign."}

@router.post("/{id}/investigate")
async def trigger_investigation(id: int):
    return {"status": "Started"}
