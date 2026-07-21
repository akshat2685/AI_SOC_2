import asyncio
import logging
import json
from typing import Dict, Any, Optional
from .playbook_parser import PlaybookParser

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
except ImportError:
    AIOKafkaConsumer = None
    AIOKafkaProducer = None

logger = logging.getLogger(__name__)

class DAGExecutor:
    """
    Executes a parsed SOAR Playbook as a Directed Acyclic Graph (DAG) using pure asyncio.
    Tracks node execution statuses and handles parallel branch execution seamlessly.
    Acts as a Kafka consumer/producer for event-driven execution.
    """
    def __init__(self, playbook_def: Dict[str, Any], tenant_id: int = 1, kafka_bootstrap: str = "localhost:9092"):
        self.playbook_def = playbook_def
        self.tenant_id = tenant_id
        self.nodes = playbook_def.get("nodes", {})
        self.edges = playbook_def.get("edges", [])
        
        self.node_status = {n: "PENDING" for n in self.nodes}
        self.node_results: Dict[str, Any] = {}
        
        self.kafka_bootstrap = kafka_bootstrap
        self.producer: Optional[Any] = None
        self.consumer: Optional[Any] = None
        
    async def init_kafka(self, sasl_username=None, sasl_password=None, security_protocol="PLAINTEXT"):
        if AIOKafkaProducer:
            try:
                self.producer = AIOKafkaProducer(
                    bootstrap_servers=self.kafka_bootstrap,
                    sasl_mechanism="PLAIN" if sasl_username else None,
                    sasl_plain_username=sasl_username,
                    sasl_plain_password=sasl_password,
                    security_protocol=security_protocol
                )
                await self.producer.start()
                if AIOKafkaConsumer:
                    self.consumer = AIOKafkaConsumer(
                        "soar.playbook.triggered",
                        bootstrap_servers=self.kafka_bootstrap,
                        sasl_mechanism="PLAIN" if sasl_username else None,
                        sasl_plain_username=sasl_username,
                        sasl_plain_password=sasl_password,
                        security_protocol=security_protocol
                    )
                    await self.consumer.start()
            except Exception as e:
                logger.warning(f"Failed to start Kafka clients: {e}")

    async def close_kafka(self):
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
            
    async def publish_event(self, topic: str, event_data: dict):
        if self.producer:
            try:
                await self.producer.send_and_wait(topic, json.dumps(event_data).encode("utf-8"))
            except Exception as e:
                logger.warning(f"Failed to publish event to {topic}: {e}")
        
        self.node_status = {n: "PENDING" for n in self.nodes}
        self.node_results: Dict[str, Any] = {}
        
    async def execute(self, initial_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the playbook DAG based on the initial context.
        Uses asyncio to run independent nodes concurrently.
        """
        context = initial_context.copy()
        
        # Build dependency graph
        dependencies = {n: [] for n in self.nodes}
        for edge in self.edges:
            dependencies[edge["to"]].append(edge["from"])
            
        # Events to signal node completion
        completion_events = {n: asyncio.Event() for n in self.nodes}
        
        async def run_node(node_id: str):
            # Wait for all dependencies to finish
            for dep in dependencies[node_id]:
                await completion_events[dep].wait()
                # If any dependency failed, this node inherently fails (basic behavior)
                if self.node_status[dep] == "FAILED":
                    self.node_status[node_id] = "FAILED"
                    self.node_results[node_id] = {"error": f"Dependency {dep} failed"}
                    completion_events[node_id].set()
                    return
                    
            self.node_status[node_id] = "RUNNING"
            node_data = self.nodes[node_id]
            
            try:
                # Interpolate inputs with the current context
                inputs = PlaybookParser.interpolate_variables(node_data.get("inputs", {}), context)
                
                # Execute the actual node action (mocked for Sprint 1 foundation)
                result = await self._execute_action(node_data.get("action"), inputs)
                
                self.node_results[node_id] = result
                # Inject result back into context for downstream nodes (e.g. node_1.result_key)
                context[f"node_{node_id}"] = result 
                self.node_status[node_id] = "SUCCESS"
            except Exception as e:
                logger.error(f"Error executing node {node_id}: {e}")
                self.node_results[node_id] = {"error": str(e)}
                self.node_status[node_id] = "FAILED"
            finally:
                # Signal downstream nodes that this node is done
                completion_events[node_id].set()

        # Spawn a task for each node. 
        # The dependencies handle the correct execution order (topological sequence via wait()).
        tasks = [asyncio.create_task(run_node(n)) for n in self.nodes]
        await asyncio.gather(*tasks)
        
        overall_status = "SUCCESS" if all(s == "SUCCESS" for s in self.node_status.values()) else "FAILED"
        
        return {
            "status": overall_status,
            "node_status": self.node_status,
            "results": self.node_results,
            "final_context": context
        }
        
    async def _execute_action(self, action: str, inputs: Dict[str, Any]) -> Any:
        """
        Placeholder for actual action execution logic to be integrated in future sprints.
        Simulates I/O bound execution.
        """
        await asyncio.sleep(0.01)
        return {"status": "ok", "action_executed": action, "processed_inputs": inputs}
