import asyncio
import json
import hmac
import hashlib
import structlog
from datetime import datetime
import httpx
from core.crypto import envelope_crypto
from core.repository import SessionLocal

logger = structlog.get_logger(__name__)

async def deliver_webhook(tenant_id: int, url: str, secret_encrypted: str, payload: dict, history_id: int):
    if not url.startswith("https://"):
        logger.error(f"Webhook URL must start with https://, got {url}")
        await _update_history_status(history_id, "failed", 1, "Insecure URL (HTTP)")
        return
        
    try:
        with SessionLocal() as db:
            secret_ba = envelope_crypto.decrypt(tenant_id, secret_encrypted, db)
    except Exception as e:
        logger.error(f"Failed to decrypt webhook secret for tenant {tenant_id}: {e}")
        await _update_history_status(history_id, "failed", 1, "Failed to decrypt secret")
        return

    body_bytes = json.dumps(payload).encode('utf-8')
    signature = hmac.new(secret_ba, body_bytes, hashlib.sha256).hexdigest()
    
    # Securely wipe the secret from memory
    for i in range(len(secret_ba)):
        secret_ba[i] = 0

    headers = {
        "Content-Type": "application/json",
        "X-Edysor-Signature": f"sha256={signature}"
    }

    async with httpx.AsyncClient() as client:
        backoffs = [10, 60, 300]
        attempts = 0
        error_msg = ""
        
        for delay in backoffs:
            attempts += 1
            try:
                response = await client.post(url, content=body_bytes, headers=headers, timeout=10.0)
                if 200 <= response.status_code < 300:
                    await _update_history_status(history_id, "delivered", attempts, None)
                    return
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
            except Exception as e:
                error_msg = str(e)
                
            await _update_history_status(history_id, "retrying", attempts, error_msg)
            await asyncio.sleep(delay)
            
        await _update_history_status(history_id, "dead_lettered", attempts, error_msg)

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
            delivered_at = datetime.utcnow() if status == "delivered" else None
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
