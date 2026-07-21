import yaml
import json
import re
from typing import Dict, Any, List

class PlaybookValidationError(Exception):
    """Exception raised for errors in playbook validation."""
    pass

class PlaybookParser:
    """
    Parses and validates SOAR playbooks defined in YAML or JSON.
    Ensures structural integrity and detects cyclical dependencies (DAG enforcement).
    Provides basic {{ variable }} interpolation.
    """
    def __init__(self, content: str, format: str = "yaml"):
        self.content = content
        self.format = format
        self.playbook: Dict[str, Any] = {}
        
    def parse(self) -> Dict[str, Any]:
        if self.format == "yaml":
            try:
                self.playbook = yaml.safe_load(self.content)
            except yaml.YAMLError as e:
                raise PlaybookValidationError(f"Invalid YAML: {e}")
        elif self.format == "json":
            try:
                self.playbook = json.loads(self.content)
            except json.JSONDecodeError as e:
                raise PlaybookValidationError(f"Invalid JSON: {e}")
        else:
            raise PlaybookValidationError(f"Unsupported format: {self.format}")
            
        self._validate_structure()
        self._detect_cycles()
        return self.playbook

    def _validate_structure(self):
        if not isinstance(self.playbook, dict):
            raise PlaybookValidationError("Playbook must be a dictionary")
        if "nodes" not in self.playbook:
            raise PlaybookValidationError("Playbook must contain 'nodes'")
        
        nodes = self.playbook.get("nodes", {})
        if not isinstance(nodes, dict):
            raise PlaybookValidationError("'nodes' must be a dictionary mapping node_id to node_data")

        edges = self.playbook.get("edges", [])
        if not isinstance(edges, list):
            raise PlaybookValidationError("'edges' must be a list of connections")
            
        for edge in edges:
            if "from" not in edge or "to" not in edge:
                raise PlaybookValidationError(f"Edge missing 'from' or 'to': {edge}")
            if edge["from"] not in nodes:
                raise PlaybookValidationError(f"Edge 'from' references unknown node: {edge['from']}")
            if edge["to"] not in nodes:
                raise PlaybookValidationError(f"Edge 'to' references unknown node: {edge['to']}")

    def _detect_cycles(self):
        """
        Uses Kahn's algorithm to detect cycles in the directed graph.
        """
        nodes = self.playbook.get("nodes", {})
        edges = self.playbook.get("edges", [])
        
        adj = {node_id: [] for node_id in nodes}
        in_degree = {node_id: 0 for node_id in nodes}
        
        for edge in edges:
            adj[edge["from"]].append(edge["to"])
            in_degree[edge["to"]] += 1
            
        queue = [n for n, deg in in_degree.items() if deg == 0]
        visited_count = 0
        
        while queue:
            curr = queue.pop(0)
            visited_count += 1
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    
        if visited_count != len(nodes):
            raise PlaybookValidationError("Cycle detected in playbook execution graph. Playbooks must be a DAG.")

    @staticmethod
    def interpolate_variables(data: Any, context: Dict[str, Any]) -> Any:
        """
        Recursively interpolate {{ variable.path }} markers in the data structure
        using the provided context dictionary.
        """
        if isinstance(data, str):
            def replacer(match):
                var_name = match.group(1).strip()
                parts = var_name.split('.')
                val = context
                try:
                    for part in parts:
                        if isinstance(val, list) and part.isdigit():
                            val = val[int(part)]
                        else:
                            val = val[part]
                    return str(val)
                except (KeyError, TypeError):
                    return match.group(0) 
                    
            return re.sub(r'\{\{(.*?)\}\}', replacer, data)
        elif isinstance(data, dict):
            return {k: PlaybookParser.interpolate_variables(v, context) for k, v in data.items()}
        elif isinstance(data, list):
            return [PlaybookParser.interpolate_variables(item, context) for item in data]
        else:
            return data
