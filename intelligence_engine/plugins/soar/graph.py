from typing import Dict, Any
from .state import IncidentState
from .supervisor import SupervisorNode
from .nodes import InvestigationNode, ContainmentNode, NotificationNode

class WorkflowEngine:
    def __init__(self):
        self.supervisor = SupervisorNode()
        self.nodes = {
            "investigate": InvestigationNode(),
            "contain": ContainmentNode(),
            "notify": NotificationNode()
        }
    
    def run(self, initial_state: IncidentState) -> IncidentState:
        current_state = initial_state.copy()
        
        while True:
            # 1. Supervisor routing
            routing_update = self.supervisor.determine_next(current_state)
            current_state.update(routing_update)
            
            next_node = current_state.get("next_node")
            
            if next_node == "end":
                break
                
            if next_node == "wait":
                # HITL Checkpoint - wait state. Engine stops here.
                # In real scenario, Event Bus will trigger resume.
                break
                
            # 2. Execute selected node
            node = self.nodes.get(next_node)
            if node:
                state_update = node.execute(current_state)
                # Update current state with results
                for key, value in state_update.items():
                    current_state[key] = value
            else:
                raise ValueError(f"Unknown node: {next_node}")
                
        return current_state
