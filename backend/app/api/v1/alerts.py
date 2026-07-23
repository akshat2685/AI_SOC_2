from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
import structlog

from app.infrastructure.database import get_db
from app.domain.models import Alert, Incident
from app.core.auth import current_tenant_id
from app.application.audit_logger import audit_logger
from app.api.middleware.rate_limit_middleware import limiter
from intelligence_engine.agents.soc_orchestrator import run_orchestrator

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("")
@limiter.limit("100/minute")
async def get_alerts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Get alerts for the current tenant (with pagination and filtering)."""
    tenant_id = current_tenant_id.get() or 1
    
    try:
        result = await db.execute(
            select(Alert)
            .where(Alert.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .order_by(Alert.timestamp.desc())
        )
        alerts = result.scalars().all()
        
        logger.info(
            "alerts_fetched",
            tenant_id=tenant_id,
            count=len(alerts),
            skip=skip,
            limit=limit
        )
        
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
                "incident_id": a.incident_id,
                "source": a.source,
            } for a in alerts
        ]
    except Exception as e:
        logger.error("alerts_fetch_failed", tenant_id=tenant_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch alerts")


@router.get("/{id}/details")
async def get_alert_details(
    id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get detailed information for a specific alert."""
    tenant_id = current_tenant_id.get() or 1
    
    try:
        result = await db.execute(
            select(Alert).where(
                Alert.id == id,
                Alert.tenant_id == tenant_id
            )
        )
        alert = result.scalars().first()
        
        if not alert:
            logger.warning("alert_not_found", alert_id=id, tenant_id=tenant_id)
            raise HTTPException(status_code=404, detail="Alert not found")
        
        logger.info("alert_details_fetched", alert_id=id, tenant_id=tenant_id)
        
        return {
            "id": alert.id,
            "title": alert.rule_name,
            "description": alert.description,
            "timestamp": alert.timestamp.isoformat(),
            "source": alert.source,
            "tenant_id": alert.tenant_id,
            "incident_id": alert.incident_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "alert_details_fetch_failed",
            alert_id=id,
            tenant_id=tenant_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to fetch alert details")


@router.get("/{id}/investigation")
async def get_alert_investigation(
    id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get investigation status and results for an alert."""
    tenant_id = current_tenant_id.get() or 1
    
    try:
        result = await db.execute(
            select(Alert).where(
                Alert.id == id,
                Alert.tenant_id == tenant_id
            )
        )
        alert = result.scalars().first()
        
        if not alert:
            logger.warning("alert_not_found_for_investigation", alert_id=id, tenant_id=tenant_id)
            raise HTTPException(status_code=404, detail="Alert not found")
        
        if not alert.incident_id:
            logger.info("investigation_not_started", alert_id=id)
            return {
                "status": "not_started",
                "summary": "Investigation has not been initiated for this alert",
                "alert_id": id,
            }
        
        incident_result = await db.execute(
            select(Incident).where(Incident.id == alert.incident_id)
        )
        incident = incident_result.scalars().first()
        
        if not incident:
            logger.warning("incident_not_found", incident_id=alert.incident_id)
            return {
                "status": "error",
                "summary": "Incident record not found",
                "alert_id": id,
            }
        
        logger.info(
            "investigation_fetched",
            alert_id=id,
            incident_id=incident.id,
            status=incident.status
        )
        
        return {
            "status": incident.status.value if incident.status else "unknown",
            "summary": incident.description,
            "severity": incident.severity.value if incident.severity else "unknown",
            "created_at": incident.created_at.isoformat(),
            "updated_at": incident.created_at.isoformat(),
            "alert_id": id,
            "incident_id": incident.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "investigation_fetch_failed",
            alert_id=id,
            tenant_id=tenant_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to fetch investigation")


@router.post("/{id}/investigate", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("50/minute")
async def trigger_investigation(
    request: Request,
    id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger an investigation for an alert (async, returns 202 Accepted)."""
    tenant_id = current_tenant_id.get() or 1
    user_id = None
    
    try:
        result = await db.execute(
            select(Alert).where(
                Alert.id == id,
                Alert.tenant_id == tenant_id
            )
        )
        alert = result.scalars().first()
        
        if not alert:
            logger.warning("alert_not_found_for_investigation", alert_id=id, tenant_id=tenant_id)
            raise HTTPException(status_code=404, detail="Alert not found")
        
        alert_data = {
            "id": alert.id,
            "source": alert.source,
            "rule_name": alert.rule_name,
            "description": alert.description,
            "timestamp": alert.timestamp.isoformat(),
            "tenant_id": tenant_id,
        }
        
        background_tasks.add_task(
            run_orchestrator,
            alert_id=str(alert.id),
            alert_data=alert_data,
            hitl_level=1,
        )
        
        audit_logger.emit(
            action="investigation_triggered",
            tenant_id=tenant_id,
            user_id=user_id,
            details={
                "alert_id": id,
                "source": alert.source,
                "rule_name": alert.rule_name,
            }
        )
        
        logger.info(
            "investigation_triggered",
            alert_id=id,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        return {
            "status": "investigation_started",
            "alert_id": id,
            "message": "Investigation has been queued and will begin shortly",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "investigation_trigger_failed",
            alert_id=id,
            tenant_id=tenant_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to trigger investigation"
        )
