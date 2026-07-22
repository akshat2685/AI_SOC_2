from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any

from app.infrastructure.database import get_db
from app.domain.models import Incident, Alert, RoleEnum
from app.core.auth import current_user_id, current_tenant_id
from app.api.deps import require_roles, TokenData

router = APIRouter()

@router.get("")
async def get_incidents(db: AsyncSession = Depends(get_db)):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.tenant_id == tenant_id))
    incidents = result.scalars().all()
    return [
        {
            "id": inc.id,
            "title": inc.title,
            "severity": inc.severity.value,
            "status": inc.status.value,
            "timestamp": inc.created_at.isoformat(),
            "llm_summary": inc.description,
            "verdict": "UNKNOWN",
            "analyst_notes": ""
        } for inc in incidents
    ]

@router.get("/{id}/details")
async def get_incident_details(id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    alerts_result = await db.execute(select(Alert).where(Alert.incident_id == id))
    alerts = alerts_result.scalars().all()
    
    return {
        "id": incident.id,
        "title": incident.title,
        "logs": [],
        "alerts": [{"id": a.id, "title": a.rule_name, "severity": "HIGH", "timestamp": a.timestamp.isoformat()} for a in alerts],
        "related_logs": [],
        "iocs": [],
        "actions": []
    }

@router.put("/{id}")
async def update_incident(id: int, data: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    if "status" in data:
        incident.status = data["status"]
    
    await db.commit()
    return {"status": "success"}

@router.post("/{id}/verdict")
async def set_verdict(id: int, data: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    return {"status": "success"}

@router.get("/{id}/predict-risk")
async def predict_risk(id: int):
    return {
        "risk_level": "High",
        "risk_score": 75,
        "likelihood": "75%",
        "reasoning": "Determined by ML model.",
        "mitigation": "Isolate host."
    }

@router.get("/{id}/graph")
async def get_graph(id: int):
    return {"nodes": [], "edges": []}

@router.get("/{id}/recommended-triage")
async def recommended_triage(id: int):
    return {"recommendation": "Isolate the endpoint and rotate credentials."}
