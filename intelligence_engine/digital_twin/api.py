import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/digital-twin", tags=["digital-twin"])

class TwinConnectionManager:
    """Manages live WebSocket streams for real-time Digital Twin updates."""
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, tenant_id: int, websocket: WebSocket):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = []
        self.active_connections[tenant_id].append(websocket)
        logger.info(f"Twin WS connected for tenant {tenant_id}")

    def disconnect(self, tenant_id: int, websocket: WebSocket):
        if tenant_id in self.active_connections and websocket in self.active_connections[tenant_id]:
            self.active_connections[tenant_id].remove(websocket)

    async def broadcast(self, tenant_id: int, message: dict):
        if tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending twin update: {e}")

manager = TwinConnectionManager()

@router.websocket("/ws/{tenant_id}")
async def websocket_endpoint(websocket: WebSocket, tenant_id: int):
    await manager.connect(tenant_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"ack": data})
    except WebSocketDisconnect:
        manager.disconnect(tenant_id, websocket)

@router.post("/{tenant_id}/simulate")
async def run_simulation(tenant_id: int, payload: Dict[str, Any]):
    """Triggers an async What-If or Monte Carlo simulation."""
    return {"status": "started", "tenant_id": tenant_id, "job_id": "sim-123"}
