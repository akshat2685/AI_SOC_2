from typing import Dict, Any, List

class PlaybookEngine:
    def __init__(self):
        self.pending_approvals = {}
        
    def execute_playbook(self, playbook_name: str, alert: Dict[str, Any]) -> Dict[str, Any]:
        if playbook_name == 'Credential Attack':
            return self._credential_attack_playbook(alert)
        elif playbook_name == 'Malware':
            return self._malware_playbook(alert)
        else:
            return {"status": "error", "message": f"Unknown playbook: {playbook_name}"}
            
    def _credential_attack_playbook(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        user = alert.get('user')
        if not user:
            return {"status": "failed", "message": "No user specified in alert."}
            
        print(f"[Playbook: Credential Attack] Initiating response for user: {user}")
        # Request approval to block user
        approval_id = f"CA_{user}_{alert.get('id', 'unknown')}"
        self.pending_approvals[approval_id] = {
            'action': 'block_user',
            'target': user,
            'alert': alert
        }
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "message": f"Approval required to block user {user}."
        }
        
    def _malware_playbook(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        host = alert.get('host')
        if not host:
            return {"status": "failed", "message": "No host specified in alert."}
            
        print(f"[Playbook: Malware] Initiating response for host: {host}")
        # Automatic containment, then request approval for wiping
        print(f"[Playbook: Malware] Automatically isolating host {host} from network.")
        
        approval_id = f"MW_{host}_{alert.get('id', 'unknown')}"
        self.pending_approvals[approval_id] = {
            'action': 'wipe_host',
            'target': host,
            'alert': alert
        }
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "message": f"Host isolated. Approval required to wipe host {host}."
        }
        
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
