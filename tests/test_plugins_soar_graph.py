import pytest
import os
import sys

# Ensure AI_SOC_2 root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from intelligence_engine.plugins.soar.state import IncidentState
from intelligence_engine.plugins.soar.interfaces import IActionNode
from intelligence_engine.plugins.soar.nodes import InvestigationNode, ContainmentNode, NotificationNode
from intelligence_engine.plugins.soar.supervisor import SupervisorNode
from intelligence_engine.plugins.soar.graph import WorkflowEngine


def test_investigation_node():
    node = InvestigationNode()
    state: IncidentState = {
        "incident_id": "1",
        "alert_data": {},
        "context": {},
        "playbook_name": "test",
        "actions_taken": [],
        "hitl_status": None,
        "next_node": None
    }
    update = node.execute(state)
    assert update["context"]["investigation_details"] == "Gathered initial threat intelligence"
    assert "investigation_completed" in update["actions_taken"]


def test_containment_node_approved():
    node = ContainmentNode()
    state: IncidentState = {
        "incident_id": "1",
        "alert_data": {},
        "context": {},
        "playbook_name": "test",
        "actions_taken": [],
        "hitl_status": "Approved",
        "next_node": None
    }
    update = node.execute(state)
    assert "containment_executed" in update["actions_taken"]
    assert update["hitl_status"] == "Completed"


def test_containment_node_rejected():
    node = ContainmentNode()
    state: IncidentState = {
        "incident_id": "1",
        "alert_data": {},
        "context": {},
        "playbook_name": "test",
        "actions_taken": [],
        "hitl_status": "Rejected",
        "next_node": None
    }
    update = node.execute(state)
    assert "containment_rejected" in update["actions_taken"]
    assert update["hitl_status"] == "Completed"


def test_containment_node_pending():
    node = ContainmentNode()
    state: IncidentState = {
        "incident_id": "1",
        "alert_data": {},
        "context": {},
        "playbook_name": "test",
        "actions_taken": [],
        "hitl_status": None,
        "next_node": None
    }
    update = node.execute(state)
    assert "containment_pending_hitl" in update["actions_taken"]
    assert update["hitl_status"] == "Pending"


def test_notification_node():
    node = NotificationNode()
    state: IncidentState = {
        "incident_id": "1",
        "alert_data": {},
        "context": {},
        "playbook_name": "test",
        "actions_taken": [],
        "hitl_status": None,
        "next_node": None
    }
    update = node.execute(state)
    assert "notification_sent" in update["actions_taken"]


def test_supervisor_node():
    supervisor = SupervisorNode()
    state: IncidentState = {
        "incident_id": "1",
        "alert_data": {},
        "context": {},
        "playbook_name": "test",
        "actions_taken": [],
        "hitl_status": None,
        "next_node": None
    }
    
    # 1. Start -> investigate
    update = supervisor.determine_next(state)
    assert update["next_node"] == "investigate"
    
    # 2. After investigation -> contain
    state["actions_taken"] = ["investigation_completed"]
    update = supervisor.determine_next(state)
    assert update["next_node"] == "contain"
    
    # 3. Contain pending -> wait
    state["hitl_status"] = "Pending"
    update = supervisor.determine_next(state)
    assert update["next_node"] == "wait"
    
    # 4. Contain completed -> notify
    state["actions_taken"] = ["investigation_completed", "containment_executed"]
    state["hitl_status"] = "Completed"
    update = supervisor.determine_next(state)
    assert update["next_node"] == "notify"
    
    # 5. After notification -> end
    state["actions_taken"] = ["investigation_completed", "containment_executed", "notification_sent"]
    update = supervisor.determine_next(state)
    assert update["next_node"] == "end"


def test_workflow_engine_full_run():
    engine = WorkflowEngine()
    initial_state: IncidentState = {
        "incident_id": "123",
        "alert_data": {"type": "malware"},
        "context": {},
        "playbook_name": "malware_playbook",
        "actions_taken": [],
        "hitl_status": None,
        "next_node": None
    }
    
    # First run will stop at 'wait' (Pending HITL)
    state = engine.run(initial_state)
    assert state["next_node"] == "wait"
    assert state["hitl_status"] == "Pending"
    assert "investigation_completed" in state["actions_taken"]
    assert "containment_pending_hitl" in state["actions_taken"]
    assert "containment_executed" not in state["actions_taken"]
    
    # Simulate HITL approval and run again
    state["hitl_status"] = "Approved"
    final_state = engine.run(state)
    assert final_state["next_node"] == "end"
    assert final_state["hitl_status"] == "Completed"
    assert "containment_executed" in final_state["actions_taken"]
    assert "notification_sent" in final_state["actions_taken"]

def test_workflow_engine_full_run_rejected():
    engine = WorkflowEngine()
    initial_state: IncidentState = {
        "incident_id": "124",
        "alert_data": {"type": "suspicious_login"},
        "context": {},
        "playbook_name": "login_playbook",
        "actions_taken": [],
        "hitl_status": None,
        "next_node": None
    }
    
    # First run will stop at 'wait'
    state = engine.run(initial_state)
    assert state["next_node"] == "wait"
    
    # Simulate HITL rejection
    state["hitl_status"] = "Rejected"
    final_state = engine.run(state)
    assert final_state["next_node"] == "end"
    assert final_state["hitl_status"] == "Completed"
    assert "containment_rejected" in final_state["actions_taken"]
    assert "notification_sent" in final_state["actions_taken"]
