import asyncio
import json
import structlog
import time
import uuid
import copy
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

class AgentProfile(BaseModel):
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_name: str
    capabilities: List[str]
    zone: str
    status: str = "active"
    last_seen: float = Field(default_factory=time.time)

class MeshClient(ABC):
    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def register_agent(self, profile: AgentProfile) -> None:
        pass

    @abstractmethod
    async def get_active_agents(self, capability: Optional[str] = None) -> List[AgentProfile]:
        pass

    @abstractmethod
    async def publish(self, subject: str, payload: dict) -> None:
        pass

    @abstractmethod
    async def request(self, subject: str, payload: dict, timeout: float = 5.0) -> dict:
        pass

    @abstractmethod
    async def subscribe(self, subject: str, handler: Callable[[dict], Any]) -> Any:
        pass


class NatsMeshClient(MeshClient):
    def __init__(self, nats_url: str):
        self.nats_url = nats_url
        self.nc = None
        self._registry: Dict[str, AgentProfile] = {}
        self._registry_lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._profile: Optional[AgentProfile] = None

    async def connect(self) -> None:
        try:
            import nats
        except ImportError:
            raise ImportError("nats-py is required for NatsMeshClient. Install with 'pip install nats-py'")
        self.nc = await nats.connect(self.nats_url)
        await self.nc.subscribe("mesh.discovery.heartbeat", cb=self._handle_heartbeat)

    async def disconnect(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self.nc:
            await self.nc.close()

    async def register_agent(self, profile: AgentProfile) -> None:
        self._profile = profile
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                if self.nc and self._profile:
                    self._profile.last_seen = time.time()
                    payload = self._profile.model_dump()
                    await self.publish("mesh.discovery.heartbeat", payload)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
            await asyncio.sleep(10)

    async def _handle_heartbeat(self, msg) -> None:
        try:
            data = json.loads(msg.data.decode())
            data.pop('last_seen', None)
            profile = AgentProfile(**data)
            profile.last_seen = time.time()
            async with self._registry_lock:
                self._registry[profile.agent_id] = profile
        except Exception as e:
            logger.error(f"Error handling heartbeat: {e}")

    async def get_active_agents(self, capability: Optional[str] = None) -> List[AgentProfile]:
        now = time.time()
        active = []
        async with self._registry_lock:
            for aid, prof in list(self._registry.items()):
                if now - prof.last_seen > 30:
                    del self._registry[aid]
                else:
                    if capability is None or capability in prof.capabilities:
                        active.append(prof)
        return active

    async def publish(self, subject: str, payload: dict) -> None:
        if not self.nc:
            raise ConnectionError("Not connected to NATS")
        data = json.dumps(payload).encode()
        await self.nc.publish(subject, data)

    async def request(self, subject: str, payload: dict, timeout: float = 5.0) -> dict:
        if not self.nc:
            raise ConnectionError("Not connected to NATS")
        data = json.dumps(payload).encode()
        response = await self.nc.request(subject, data, timeout=timeout)
        return json.loads(response.data.decode())

    async def subscribe(self, subject: str, handler: Callable[[dict], Any]) -> Any:
        if not self.nc:
            raise ConnectionError("Not connected to NATS")
        
        async def _wrapper(msg):
            try:
                payload = json.loads(msg.data.decode())
                result = await handler(payload)
                if msg.reply and result is not None:
                    await self.nc.publish(msg.reply, json.dumps(result).encode())
            except Exception as e:
                logger.error(f"Error handling message on {subject}: {e}")

        return await self.nc.subscribe(subject, cb=_wrapper)


class LocalMeshClient(MeshClient):
    _shared_registry: Dict[str, AgentProfile] = {}
    _shared_registry_lock = asyncio.Lock()
    _shared_subscribers: Dict[str, List[Callable]] = {}

    def __init__(self):
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._profile: Optional[AgentProfile] = None
        self._connected = False
        self._local_subscriptions: List[tuple] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Cleanup local subscriptions on disconnect
        for subject, wrapper in self._local_subscriptions:
            if subject in LocalMeshClient._shared_subscribers:
                if wrapper in LocalMeshClient._shared_subscribers[subject]:
                    LocalMeshClient._shared_subscribers[subject].remove(wrapper)
        self._local_subscriptions.clear()

    async def register_agent(self, profile: AgentProfile) -> None:
        self._profile = profile
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        while self._connected:
            try:
                if self._profile:
                    self._profile.last_seen = time.time()
                    async with LocalMeshClient._shared_registry_lock:
                        LocalMeshClient._shared_registry[self._profile.agent_id] = self._profile
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in local heartbeat: {e}")
            await asyncio.sleep(10)

    async def get_active_agents(self, capability: Optional[str] = None) -> List[AgentProfile]:
        now = time.time()
        active = []
        async with LocalMeshClient._shared_registry_lock:
            for aid, prof in list(LocalMeshClient._shared_registry.items()):
                if now - prof.last_seen > 30:
                    del LocalMeshClient._shared_registry[aid]
                else:
                    if capability is None or capability in prof.capabilities:
                        active.append(prof)
        return active

    async def publish(self, subject: str, payload: dict) -> None:
        if not self._connected:
            raise ConnectionError("Not connected")
        if subject in LocalMeshClient._shared_subscribers:
            for handler in LocalMeshClient._shared_subscribers[subject]:
                asyncio.create_task(self._safe_handle(handler, copy.deepcopy(payload)))

    async def request(self, subject: str, payload: dict, timeout: float = 5.0) -> dict:
        if not self._connected:
            raise ConnectionError("Not connected")
        
        reply_subject = f"_INBOX.{uuid.uuid4().hex}"
        reply_queue = asyncio.Queue()
        
        async def _reply_handler(msg: dict):
            await reply_queue.put(msg)

        if reply_subject not in LocalMeshClient._shared_subscribers:
            LocalMeshClient._shared_subscribers[reply_subject] = []
        LocalMeshClient._shared_subscribers[reply_subject].append(_reply_handler)

        msg_with_reply = {"__payload__": payload, "__reply__": reply_subject}

        await self.publish(subject, msg_with_reply)

        try:
            return await asyncio.wait_for(reply_queue.get(), timeout=timeout)
        finally:
            if reply_subject in LocalMeshClient._shared_subscribers:
                del LocalMeshClient._shared_subscribers[reply_subject]

    async def subscribe(self, subject: str, handler: Callable[[dict], Any]) -> Any:
        if not self._connected:
            raise ConnectionError("Not connected")
        
        async def _wrapper(payload_or_msg: dict):
            if isinstance(payload_or_msg, dict) and "__reply__" in payload_or_msg:
                actual_payload = payload_or_msg.get("__payload__", {})
                reply_subject = payload_or_msg["__reply__"]
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(actual_payload)
                else:
                    result = handler(actual_payload)
                if result is not None:
                    await self.publish(reply_subject, result)
            else:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload_or_msg)
                else:
                    handler(payload_or_msg)

        if subject not in LocalMeshClient._shared_subscribers:
            LocalMeshClient._shared_subscribers[subject] = []
        LocalMeshClient._shared_subscribers[subject].append(_wrapper)
        self._local_subscriptions.append((subject, _wrapper))
        return _wrapper

    async def _safe_handle(self, handler, payload):
        try:
            await handler(payload)
        except Exception as e:
            logger.error(f"Error handling local message: {e}")
