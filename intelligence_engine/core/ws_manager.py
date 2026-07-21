import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
import redis.asyncio as redis
from .config import get_settings

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self.settings = get_settings()
        self.redis_client = redis.from_url(self.settings.db.redis_url, decode_responses=True)
        self.redis_tasks: Dict[int, asyncio.Task] = {}
        self.ping_task = None

    async def connect(self, websocket: WebSocket, token: str) -> int:
        if self.ping_task is None or self.ping_task.done():
            self.ping_task = asyncio.create_task(self._ping_pong_heartbeat())
        await websocket.accept()
        try:
            # We don't verify signature here as we just extract payload, but in prod we should.
            # Security says: JWT Auth Extract the JWT from the token query param during handshake. Reject unauthenticated connections with close code 4001. Extract the tenant_id from the valid JWT.
            payload = jwt.decode(
                token,
                self.settings.security.secret_key,
                algorithms=[self.settings.security.algorithm],
                options={"verify_signature": True}
            )
            tenant_id = payload.get("tenant_id")
            if tenant_id is None:
                await websocket.close(code=4001, reason="Invalid token: missing tenant_id")
                return None
            
            tenant_id = int(tenant_id)
            if tenant_id not in self.active_connections:
                self.active_connections[tenant_id] = set()
                self.redis_tasks[tenant_id] = asyncio.create_task(self._listen_to_redis(tenant_id))

            self.active_connections[tenant_id].add(websocket)
            return tenant_id
        except JWTError as e:
            logger.error(f"JWT decode error: {e}")
            await websocket.close(code=4001, reason="Unauthorized")
            return None

    def disconnect(self, websocket: WebSocket, tenant_id: int):
        if tenant_id in self.active_connections and websocket in self.active_connections[tenant_id]:
            self.active_connections[tenant_id].remove(websocket)
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]
                if tenant_id in self.redis_tasks:
                    self.redis_tasks[tenant_id].cancel()
                    del self.redis_tasks[tenant_id]

    async def _listen_to_redis(self, tenant_id: int):
        channel_name = f"notify:{tenant_id}"
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(channel_name)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if tenant_id in self.active_connections:
                        dead_sockets = set()
                        for ws in self.active_connections[tenant_id]:
                            try:
                                await ws.send_text(data)
                            except Exception as e:
                                logger.error(f"Error sending message to ws: {e}")
                                dead_sockets.add(ws)
                        
                        for ws in dead_sockets:
                            self.disconnect(ws, tenant_id)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(channel_name)
        except Exception as e:
            logger.error(f"Redis listen error for tenant {tenant_id}: {e}")

    async def _ping_pong_heartbeat(self):
        while True:
            await asyncio.sleep(30)
            for tenant_id, websockets in list(self.active_connections.items()):
                dead_sockets = set()
                for ws in websockets:
                    try:
                        await ws.send_json({"type": "ping"})
                    except Exception:
                        dead_sockets.add(ws)
                for ws in dead_sockets:
                    self.disconnect(ws, tenant_id)

manager = ConnectionManager()
