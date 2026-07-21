import asyncio
import pytest
import time
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from core.mesh import LocalMeshClient, AgentProfile, NatsMeshClient

@pytest.fixture
def mock_nats_module():
    mock_nats = MagicMock()
    mock_nc = AsyncMock()
    mock_nats.connect.return_value = mock_nc
    
    with patch.dict(sys.modules, {'nats': mock_nats}):
        yield mock_nats, mock_nc

@pytest.mark.asyncio
async def test_local_mesh_discovery():
    client1 = LocalMeshClient()
    client2 = LocalMeshClient()
    
    await client1.connect()
    await client2.connect()
    
    profile1 = AgentProfile(node_name="node1", capabilities=["cap1"], zone="local")
    profile2 = AgentProfile(node_name="node2", capabilities=["cap2"], zone="local")
    
    await client1.register_agent(profile1)
    await client2.register_agent(profile2)
    
    # Allow some time for heartbeats
    await asyncio.sleep(0.1)
    
    active_agents_1 = await client1.get_active_agents()
    active_agents_2 = await client2.get_active_agents()
    
    assert len(active_agents_1) == 2
    assert len(active_agents_2) == 2
    
    # Filter by capability
    cap1_agents = await client1.get_active_agents(capability="cap1")
    assert len(cap1_agents) == 1
    assert cap1_agents[0].node_name == "node1"
    
    await client1.disconnect()
    await client2.disconnect()

@pytest.mark.asyncio
async def test_local_mesh_request_reply():
    server_client = LocalMeshClient()
    client_client = LocalMeshClient()
    
    await server_client.connect()
    await client_client.connect()
    
    async def echo_handler(payload: dict):
        return {"echo": payload.get("msg")}
    
    await server_client.subscribe("test.echo", echo_handler)
    
    response = await client_client.request("test.echo", {"msg": "hello"})
    assert response == {"echo": "hello"}
    
    await server_client.disconnect()
    await client_client.disconnect()

@pytest.mark.asyncio
async def test_local_mesh_publish_subscribe():
    pub_client = LocalMeshClient()
    sub_client = LocalMeshClient()
    
    await pub_client.connect()
    await sub_client.connect()
    
    received_messages = []
    
    async def sub_handler(payload: dict):
        received_messages.append(payload)
        
    await sub_client.subscribe("test.pubsub", sub_handler)
    
    await pub_client.publish("test.pubsub", {"event": "started"})
    
    # Allow event loop to process
    await asyncio.sleep(0.1)
    
    assert len(received_messages) == 1
    assert received_messages[0] == {"event": "started"}
    
    await pub_client.disconnect()
    await sub_client.disconnect()

@pytest.mark.asyncio
async def test_local_mesh_request_timeout():
    client = LocalMeshClient()
    await client.connect()
    
    with pytest.raises(asyncio.TimeoutError):
        await client.request("test.nonexistent", {"msg": "hello"}, timeout=0.1)
        
    await client.disconnect()

@pytest.mark.asyncio
async def test_local_mesh_agent_expiration():
    client = LocalMeshClient()
    await client.connect()
    
    profile = AgentProfile(node_name="node_expire", capabilities=[], zone="local")
    profile.last_seen = time.time() - 40 # simulate an old heartbeat
    
    async with LocalMeshClient._shared_registry_lock:
        LocalMeshClient._shared_registry[profile.agent_id] = profile
        
    active = await client.get_active_agents()
    assert len(active) == 0 # Should have expired
    
    await client.disconnect()

@pytest.mark.asyncio
async def test_nats_mesh_connect_publish(mock_nats_module):
    mock_nats, mock_nc = mock_nats_module
    
    client = NatsMeshClient("nats://localhost:4222")
    await client.connect()
    
    assert mock_nats.connect.called
    assert mock_nc.subscribe.called
    
    await client.publish("test.topic", {"key": "val"})
    mock_nc.publish.assert_called_once()
    args, kwargs = mock_nc.publish.call_args
    assert args[0] == "test.topic"
    assert b'"key": "val"' in args[1]
    
    await client.disconnect()

@pytest.mark.asyncio
async def test_nats_mesh_request(mock_nats_module):
    mock_nats, mock_nc = mock_nats_module
    
    mock_msg = MagicMock()
    mock_msg.data = b'{"status": "ok"}'
    mock_nc.request.return_value = mock_msg
    
    client = NatsMeshClient("nats://localhost:4222")
    await client.connect()
    
    resp = await client.request("test.req", {"data": "test"})
    assert resp == {"status": "ok"}
    mock_nc.request.assert_called_once()
    
    await client.disconnect()

@pytest.mark.asyncio
async def test_nats_mesh_not_connected():
    client = NatsMeshClient("nats://localhost:4222")
    # did not call connect()
    with pytest.raises(ConnectionError):
        await client.publish("topic", {})
    with pytest.raises(ConnectionError):
        await client.request("topic", {})
    with pytest.raises(ConnectionError):
        await client.subscribe("topic", lambda x: x)

@pytest.mark.asyncio
async def test_local_mesh_disconnect_does_not_affect_others():
    client1 = LocalMeshClient()
    client2 = LocalMeshClient()
    await client1.connect()
    await client2.connect()

    received = []
    await client1.subscribe("test.shared", lambda p: received.append(("client1", p)))
    await client2.subscribe("test.shared", lambda p: received.append(("client2", p)))
    
    await client1.disconnect()
    
    client3 = LocalMeshClient()
    await client3.connect()
    await client3.publish("test.shared", {"msg": "hi"})
    
    await asyncio.sleep(0.1)
    assert len(received) == 1
    assert received[0] == ("client2", {"msg": "hi"})
    
    await client2.disconnect()
    await client3.disconnect()

@pytest.mark.asyncio
async def test_local_mesh_publish_deepcopy():
    client1 = LocalMeshClient()
    client2 = LocalMeshClient()
    await client1.connect()
    await client2.connect()
    
    original_payload = {"key": "value", "nested": {"inner": 1}}
    
    async def mutator_handler(payload: dict):
        payload["key"] = "mutated"
        payload["nested"]["inner"] = 2
        
    await client2.subscribe("test.mutate", mutator_handler)
    
    await client1.publish("test.mutate", original_payload)
    await asyncio.sleep(0.1)
    
    # Original payload should be untouched due to deepcopy
    assert original_payload == {"key": "value", "nested": {"inner": 1}}
    
    await client1.disconnect()
    await client2.disconnect()
