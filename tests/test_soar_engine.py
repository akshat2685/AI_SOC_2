import pytest
import os
import sys
import asyncio

# Ensure AI_SOC_2 root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from intelligence_engine.soar.core.playbook_parser import PlaybookParser, PlaybookValidationError
from intelligence_engine.soar.core.dag_executor import DAGExecutor

class TestPlaybookParser:
    def test_parse_valid_yaml(self):
        yaml_content = """
nodes:
  node1:
    action: test_action
    inputs:
      foo: "bar"
  node2:
    action: test_action
    inputs:
      foo: "{{ node1.foo }}"
edges:
  - from: node1
    to: node2
        """
        parser = PlaybookParser(yaml_content, format="yaml")
        playbook = parser.parse()
        assert "nodes" in playbook
        assert "node1" in playbook["nodes"]
        assert len(playbook["edges"]) == 1
        
    def test_parse_missing_nodes(self):
        yaml_content = """
edges: []
        """
        parser = PlaybookParser(yaml_content, format="yaml")
        with pytest.raises(PlaybookValidationError, match="Playbook must contain 'nodes'"):
            parser.parse()
            
    def test_detect_cycle(self):
        yaml_content = """
nodes:
  node1: {}
  node2: {}
  node3: {}
edges:
  - from: node1
    to: node2
  - from: node2
    to: node3
  - from: node3
    to: node1
        """
        parser = PlaybookParser(yaml_content, format="yaml")
        with pytest.raises(PlaybookValidationError, match="Cycle detected"):
            parser.parse()

    def test_interpolate_variables(self):
        data = {
            "key1": "value1",
            "key2": "Hello {{ context.user.name }}",
            "key3": ["{{ context.items.0 }}", "static"]
        }
        context = {
            "context": {
                "user": {"name": "Alice"},
                "items": ["Item1"]
            }
        }
        result = PlaybookParser.interpolate_variables(data, context)
        assert result["key2"] == "Hello Alice"
        assert result["key3"][0] == "Item1"

class TestDAGExecutor:
    @pytest.mark.asyncio
    async def test_dag_executor_success(self):
        playbook_def = {
            "nodes": {
                "node1": {"action": "action1", "inputs": {"x": 1}},
                "node2": {"action": "action2", "inputs": {"y": "{{ node_node1.status }}"}}
            },
            "edges": [
                {"from": "node1", "to": "node2"}
            ]
        }
        executor = DAGExecutor(playbook_def)
        result = await executor.execute({"initial": "context"})
        
        assert result["status"] == "SUCCESS"
        assert result["node_status"]["node1"] == "SUCCESS"
        assert result["node_status"]["node2"] == "SUCCESS"
        
        # Check context injection and interpolation
        final_context = result["final_context"]
        assert "node_node1" in final_context
        assert result["results"]["node2"]["processed_inputs"]["y"] == "ok"
        
    @pytest.mark.asyncio
    async def test_dag_executor_dependency_failure(self):
        playbook_def = {
            "nodes": {
                "node1": {"action": "fail_action"},
                "node2": {"action": "action2"}
            },
            "edges": [
                {"from": "node1", "to": "node2"}
            ]
        }
        executor = DAGExecutor(playbook_def)
        
        async def mock_execute(action, inputs):
            if action == "fail_action":
                raise ValueError("Intentional failure")
            return {"status": "ok"}
            
        executor._execute_action = mock_execute
        
        result = await executor.execute({})
        
        assert result["status"] == "FAILED"
        assert result["node_status"]["node1"] == "FAILED"
        assert result["node_status"]["node2"] == "FAILED"
        assert "Intentional failure" in result["results"]["node1"]["error"]
        assert "Dependency node1 failed" in result["results"]["node2"]["error"]
