import asyncio
import json
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List

from core.repository import SessionLocal
from core.webhook_delivery import deliver_webhook
from core.config import get_settings
import redis.asyncio as redis

# Optional sinks simulation
async def email_sink(tenant_id: int, payload: dict, history_id: int):
    # simulate email
    await _update_history_status(history_id, "delivered", 1)

async def slack_sink(tenant_id: int, payload: dict, history_id: int):
    # simulate slack
    await _update_history_status(history_id, "delivered", 1)

async def _update_history_status(history_id: int, status: str, attempts: int, error: str = None):
    try:
        from core.repository import SessionLocal
        from sqlalchemy import text
        with SessionLocal() as session:
            update_stmt = text("""
                UPDATE notification_history
                SET status = :status, attempts = :attempts, error = :error, delivered_at = :delivered_at
                WHERE id = :history_id
            """)
            delivered_at = datetime.now(timezone.utc) if status == "delivered" else None
            session.execute(update_stmt, {
                "status": status,
                "attempts": attempts,
                "error": error,
                "delivered_at": delivered_at,
                "history_id": history_id
            })
            session.commit()
    except Exception as e:
        logger.error(f"Failed to update history {history_id}: {e}")

logger = structlog.get_logger(__name__)

SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

class NotificationRouter:
    def __init__(self):
        self.settings = get_settings()
        self.redis_client = redis.from_url(self.settings.db.redis_url, decode_responses=True)

    def _is_in_quiet_hours(self, pref) -> bool:
        if not pref.get("quiet_hours_start") or not pref.get("quiet_hours_end"):
            return False
        now = datetime.now(timezone.utc).time()
        start = pref["quiet_hours_start"]
        end = pref["quiet_hours_end"]
        if start <= end:
            return start <= now <= end
        else:
            return start <= now or now <= end

    def _meets_severity(self, min_severity: str, event_severity: str) -> bool:
        if not event_severity:
            return True # if event has no severity, assume it passes
        min_level = SEVERITY_ORDER.get(min_severity.upper(), 1)
        event_level = SEVERITY_ORDER.get(event_severity.upper(), 1)
        return event_level >= min_level

    async def route(self, tenant_id: int, event_type: str, payload: dict):
        event_severity = payload.get("severity", "LOW")
        
        with SessionLocal() as session:
            from sqlalchemy import text
            prefs_stmt = text("""
                SELECT id, channel, enabled, min_severity, quiet_hours_start, quiet_hours_end, config
                FROM notification_preferences
                WHERE tenant_id = :tenant_id AND enabled = True
            """)
            prefs = session.execute(prefs_stmt, {"tenant_id": tenant_id}).mappings().all()

            endpoints_stmt = text("""
                SELECT id, url, secret, events, is_active
                FROM webhook_endpoints
                WHERE tenant_id = :tenant_id AND is_active = True
            """)
            webhooks = session.execute(endpoints_stmt, {"tenant_id": tenant_id}).mappings().all()

        for pref in prefs:
            if not self._meets_severity(pref["min_severity"], event_severity):
                continue
            if self._is_in_quiet_hours(pref):
                continue
            
            channel = pref["channel"]
            history_id = self._create_history(tenant_id, channel, event_type, payload, session)
            
            if channel == "websocket":
                asyncio.create_task(self._websocket_sink(tenant_id, payload, history_id))
            elif channel == "email":
                asyncio.create_task(email_sink(tenant_id, payload, history_id))
            elif channel == "slack":
                asyncio.create_task(slack_sink(tenant_id, payload, history_id))
            elif channel == "webhook":
                for wh in webhooks:
                    wh_events = wh["events"] if isinstance(wh["events"], list) else json.loads(wh["events"] or "[]")
                    if event_type in wh_events or "*" in wh_events or not wh_events:
                        wh_history_id = self._create_history(tenant_id, "webhook", event_type, payload, session)
                        asyncio.create_task(deliver_webhook(tenant_id, wh["url"], wh["secret"], payload, wh_history_id))

    def _create_history(self, tenant_id: int, channel: str, event_type: str, payload: dict, session) -> int:
        from sqlalchemy import text
        insert_stmt = text("""
            INSERT INTO notification_history (tenant_id, channel, event_type, payload, status, attempts)
            VALUES (:tenant_id, :channel, :event_type, :payload, 'retrying', 0)
            RETURNING id
        """)
        with SessionLocal() as s:
            result = s.execute(insert_stmt, {
                "tenant_id": tenant_id,
                "channel": channel,
                "event_type": event_type,
                "payload": json.dumps(payload)
            })
            s.commit()
            return result.scalar()

    async def _websocket_sink(self, tenant_id: int, payload: dict, history_id: int):
        try:
            channel_name = f"notify:{tenant_id}"
            await self.redis_client.publish(channel_name, json.dumps(payload))
            await _update_history_status(history_id, "delivered", 1)
        except Exception as e:
            logger.error(f"Failed to publish to redis: {e}")
            await _update_history_status(history_id, "failed", 1, str(e))

router = NotificationRouter()
