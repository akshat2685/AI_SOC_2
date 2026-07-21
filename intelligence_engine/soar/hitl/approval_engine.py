import json
import logging
import asyncio
from typing import Dict, Any, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ApprovalEngine:
    """
    Manages Human-in-the-Loop (HITL) manual approvals for SOAR Playbooks.
    Utilizes WebSockets for real-time frontend streaming and Redis Pub/Sub for stateless scaling.
    """
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # In a real cluster, we'd use redis.Redis.pubsub()
        # For this standalone foundation, we use asyncio queues
        self.pubsub_channels: Dict[str, asyncio.Queue] = {}

    async def connect(self, tenant_id: int, websocket: WebSocket):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)
        logger.info(f"WebSocket connected for tenant {tenant_id}")

    def disconnect(self, tenant_id: int, websocket: WebSocket):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].discard(websocket)
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]
            logger.info(f"WebSocket disconnected for tenant {tenant_id}")

    async def request_approval(self, tenant_id: int, execution_id: int, node_id: str, context: Dict[str, Any]):
        """
        Invoked by the DAGExecutor when a manual approval node is reached.
        Publishes 'soar.approval.requested' to the frontend.
        """
        payload = {
            "event": "soar.approval.requested",
            "execution_id": execution_id,
            "node_id": node_id,
            "context": context
        }
        
        # Stream to WebSocket if connected
        if tenant_id in self.active_connections:
            for websocket in list(self.active_connections[tenant_id]):
                try:
                    await websocket.send_json(payload)
                except Exception as e:
                    logger.error(f"Failed to send approval request via WS: {e}")
                    self.active_connections[tenant_id].discard(websocket)
                
        # Also publish to internal pubsub for DAG resumption
        channel_key = f"approval_{execution_id}_{node_id}"
        if channel_key not in self.pubsub_channels:
            self.pubsub_channels[channel_key] = asyncio.Queue()

    async def wait_for_approval(self, execution_id: int, node_id: str) -> Dict[str, Any]:
        """
        Blocks the DAG branch until an approval response is received via WebSocket.
        """
        channel_key = f"approval_{execution_id}_{node_id}"
        if channel_key not in self.pubsub_channels:
            self.pubsub_channels[channel_key] = asyncio.Queue()
            
        # Wait for the frontend to submit an approval response
        response = await self.pubsub_channels[channel_key].get()
        del self.pubsub_channels[channel_key]
        return response

    async def resolve_approval(self, tenant_id: int, execution_id: int, node_id: str, action: str, approver_id: int):
        """
        Invoked by the WebSocket endpoint when a human responds (e.g., 'approve' or 'reject').
        Resumes the blocked DAG branch.
        """
        channel_key = f"approval_{execution_id}_{node_id}"
        if channel_key in self.pubsub_channels:
            response = {
                "action": action,
                "approver_id": approver_id
            }
            await self.pubsub_channels[channel_key].put(response)
            
            # Notify frontend of resolution
            if tenant_id in self.active_connections:
                payload = {
                    "event": "soar.approval.resolved",
                    "execution_id": execution_id,
                    "node_id": node_id,
                    "action": action
                }
                for websocket in list(self.active_connections[tenant_id]):
                    try:
                        await websocket.send_json(payload)
                    except Exception as e:
                        logger.error(f"Failed to send resolution via WS: {e}")
                        self.active_connections[tenant_id].discard(websocket)

# Global singleton for FastAPI injection
approval_engine = ApprovalEngine()
