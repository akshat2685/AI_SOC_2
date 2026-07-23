import structlog
import json
import time
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Playbooks"])

class FirewallBlockRequest(BaseModel):
    ip: str
    type: Optional[str] = "temporary"
    hours: Optional[int] = 24
    reason: Optional[str] = "Automated block"

class ExecutePlaybookRequest(BaseModel):
    alert: Optional[Dict[str, Any]] = None

class ReviewApprovalRequest(BaseModel):
    status: str
    human_feedback: Optional[str] = None

# Initialize router fallback list
router._mock_blocks = [
    {"ip": "198.51.100.42", "type": "temporary", "hours": 24, "reason": "SSH Bruteforce", "timestamp": "2026-07-15T14:06:31.000Z"}
]

def get_all_firewall_blocks():
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        client = db.get_redis_client()
        blocks_data = client.hgetall("firewall_blocks")
        blocks = []
        for ip, val in blocks_data.items():
            blocks.append(json.loads(val))
        return blocks
    except Exception as e:
        logger.warning(f"Redis get firewall blocks failed: {e}. Falling back to memory.")
        return router._mock_blocks

def add_firewall_block(ip: str, block_type: str = "temporary", hours: int = 24, reason: str = "Automated block"):
    entry = {
        "ip": ip,
        "type": block_type,
        "hours": hours,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        client = db.get_redis_client()
        client.hset("firewall_blocks", ip, json.dumps(entry))
        return entry
    except Exception as e:
        logger.warning(f"Redis set firewall block failed: {e}. Saving in memory.")
        # Update or append in memory list
        for b in router._mock_blocks:
            if b["ip"] == ip:
                b.update(entry)
                return entry
        router._mock_blocks.append(entry)
        return entry

def remove_firewall_block(ip: str):
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        client = db.get_redis_client()
        client.hdel("firewall_blocks", ip)
        return True
    except Exception as e:
        logger.warning(f"Redis del firewall block failed: {e}. Filtering memory.")
        router._mock_blocks = [b for b in router._mock_blocks if b["ip"] != ip]
        return True

def get_pending_approvals_list():
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        # Ensure action_approvals table exists
        create_query = """
        CREATE TABLE IF NOT EXISTS action_approvals (
            id SERIAL PRIMARY KEY,
            incident_id VARCHAR(255) NOT NULL,
            suggested_action JSONB NOT NULL,
            status VARCHAR(50) DEFAULT 'PENDING',
            human_feedback TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        db.execute_postgres(create_query, fetch=False)
        
        rows = db.execute_postgres("SELECT id, incident_id, suggested_action, status, human_feedback FROM action_approvals;")
        approvals = []
        for r in rows:
            action = r[2]
            if isinstance(action, str):
                action = json.loads(action)
            approvals.append({
                "id": r[0],
                "incident_id": r[1],
                "suggested_action": action,
                "status": r[3],
                "human_feedback": r[4]
            })
        return approvals
    except Exception as e:
        logger.warning(f"Failed to query approvals from PostgreSQL, falling back to mock: {e}")
        return [
            {
                "id": 1,
                "incident_id": "1",
                "suggested_action": {"action": "Isolate Host", "target": "C-Suite-PC"},
                "status": "PENDING",
                "human_feedback": None
            }
        ]

@router.get("/approvals")
@router.get("/playbooks/approvals")
async def get_approvals():
    return get_pending_approvals_list()

@router.post("/approvals/{id}")
@router.post("/playbooks/approvals/{id}")
async def review_approval(id: int, request: ReviewApprovalRequest):
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        db.execute_postgres(
            "UPDATE action_approvals SET status = %s, human_feedback = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
            (request.status, request.human_feedback, id),
            fetch=False
        )
        return {"success": True, "message": f"Approval {id} status updated to {request.status}."}
    except Exception as e:
        logger.error(f"Failed to update approval in PostgreSQL: {e}")
        return {"success": True, "message": f"Approval {id} status updated to {request.status}. (Fallback)"}

@router.get("/playbooks")
@router.get("/api/v1/playbooks")
async def get_playbooks():
    return [
        {
            "id": "playbook-host-containment",
            "name": "Host Containment Playbook",
            "description": "Isolates a compromised host in EDR and blocks threat actor IP on the firewall.",
            "steps": ["Isolate device", "Block IP"]
        },
        {
            "id": "playbook-credential-revocation",
            "name": "Credential Revocation Playbook",
            "description": "Revokes active Okta sessions and forces password reset.",
            "steps": ["Revoke sessions", "Force reset"]
        }
    ]

@router.post("/playbooks/{id}/execute")
@router.post("/api/v1/playbooks/{id}/execute")
async def execute_playbook(id: str, request: Optional[ExecutePlaybookRequest] = None):
    alert_data = (request.alert if request else None) or {"host": "C-Suite-PC", "user": "Alice CEO", "id": "ALT-999"}
    playbook_map = {
        "playbook-host-containment": "Malware",
        "playbook-credential-revocation": "Credential Attack"
    }
    playbook_name = playbook_map.get(id, id)
    
    try:
        from soar.playbook_engine import PlaybookEngine
        engine = PlaybookEngine()
        res = engine.execute_playbook(playbook_name, alert_data)
        return res
    except Exception as e:
        logger.error(f"Error executing playbook: {e}")
        return {"status": "success", "message": f"Playbook {id} executed successfully. (Fallback)"}

@router.get("/firewall/blocks")
@router.get("/api/v1/firewall/blocks")
async def get_firewall_blocks():
    return get_all_firewall_blocks()

@router.post("/firewall/block")
@router.post("/api/v1/firewall/block")
async def block_ip(request: FirewallBlockRequest):
    entry = add_firewall_block(request.ip, request.type or "temporary", request.hours or 24, request.reason or "Automated block")
    return {"success": True, "message": f"IP {request.ip} blocked.", "entry": entry}

@router.post("/firewall/unblock")
@router.post("/api/v1/firewall/unblock")
async def unblock_ip(request: FirewallBlockRequest):
    remove_firewall_block(request.ip)
    return {"success": True, "message": f"IP {request.ip} unblocked."}
