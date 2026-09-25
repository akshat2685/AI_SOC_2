"""SOAR playbook engine with a declarative playbook schema.

Playbooks are data, not branches: each playbook declares a trigger and an
ordered list of steps. A step is::

    {
        "action": "block_user",        # what to do
        "target_from": "user",         # alert field holding the target
        "approval_required": True,     # False => executed automatically
        "description": "human-readable summary",
    }

Adding a new response playbook means adding a dict entry -- no engine
changes. Unknown playbook names still return an explicit error.
"""

from typing import Dict, Any, List

PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    "Credential Attack": {
        "description": "Respond to credential-based attacks (brute force, stuffing, password spray).",
        "trigger": {"event_type": "credential_attack"},
        "approval_prefix": "CA",
        "steps": [
            {
                "action": "block_user",
                "target_from": "user",
                "approval_required": True,
                "description": "Block the compromised user account.",
            },
        ],
    },
    "Malware": {
        "description": "Respond to malware detections on a host.",
        "trigger": {"event_type": "malware"},
        "approval_prefix": "MW",
        "steps": [
            {
                "action": "isolate_host",
                "target_from": "host",
                "approval_required": False,
                "description": "Automatically isolate the host from the network.",
            },
            {
                "action": "wipe_host",
                "target_from": "host",
                "approval_required": True,
                "description": "Wipe and reimage the host.",
            },
        ],
    },
}


class PlaybookEngine:
    def __init__(self):
        self.pending_approvals = {}

    # ------------------------------------------------------------------
    # Schema API
    # ------------------------------------------------------------------
    def list_playbooks(self) -> List[Dict[str, Any]]:
        """Return name/description/trigger for every registered playbook."""
        return [
            {"name": name, "description": spec.get("description", ""), "trigger": spec.get("trigger", {})}
            for name, spec in PLAYBOOKS.items()
        ]

    def execute_playbook(self, playbook_name: str, alert: Dict[str, Any]) -> Dict[str, Any]:
        spec = PLAYBOOKS.get(playbook_name)
        if spec is None:
            return {"status": "error", "message": f"Unknown playbook: {playbook_name}"}
        return self._run_steps(playbook_name, spec, alert)

    def _run_steps(
        self, playbook_name: str, spec: Dict[str, Any], alert: Dict[str, Any]
    ) -> Dict[str, Any]:
        prefix = spec.get("approval_prefix", playbook_name[:2].upper())
        executed: List[Dict[str, Any]] = []
        for step in spec.get("steps", []):
            target_field = step.get("target_from", "")
            target = alert.get(target_field) if target_field else None
            if not target:
                return {
                    "status": "failed",
                    "message": f"No '{target_field}' specified in alert.",
                    "executed": executed,
                }
            action = step["action"]
            print(f"[Playbook: {playbook_name}] {step.get('description', action)} -> {target}")
            if step.get("approval_required"):
                approval_id = f"{prefix}_{target}_{alert.get('id', 'unknown')}"
                self.pending_approvals[approval_id] = {
                    "action": action,
                    "target": target,
                    "alert": alert,
                }
                return {
                    "status": "pending_approval",
                    "approval_id": approval_id,
                    "message": f"Approval required to {action} {target}.",
                    "executed": executed,
                }
            executed.append({"action": action, "target": target, "status": "executed"})
        return {"status": "success", "message": "All playbook steps executed.", "executed": executed}

    # ------------------------------------------------------------------
    # Approvals / rollback (unchanged semantics)
    # ------------------------------------------------------------------
    def approve_action(self, approval_id: str) -> Dict[str, Any]:
        if approval_id not in self.pending_approvals:
            return {"status": "failed", "message": "Invalid or expired approval ID."}

        action_details = self.pending_approvals.pop(approval_id)
        action = action_details['action']
        target = action_details['target']

        print(f"[Approval] Executing action {action} on {target}.")
        return {"status": "success", "message": f"Action {action} on {target} executed.", "rollback_id": f"rb_{approval_id}"}

    def rollback_action(self, rollback_id: str) -> Dict[str, Any]:
        # Simple simulation of rollback logic
        print(f"[Rollback] Rolling back action associated with {rollback_id}.")
        return {"status": "success", "message": f"Rollback {rollback_id} completed successfully."}
