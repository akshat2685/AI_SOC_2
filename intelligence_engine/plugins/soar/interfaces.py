from abc import ABC, abstractmethod
from typing import Dict, Any
from .state import IncidentState

class IActionNode(ABC):
    @abstractmethod
    def execute(self, state: IncidentState) -> Dict[str, Any]:
        """
        Executes the action and returns a dictionary with updates to the IncidentState.
        """
        pass
