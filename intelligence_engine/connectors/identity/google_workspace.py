class GoogleWorkspaceConnector:
    def __init__(self, service_account_json):
        self.service_account = service_account_json

    def parse_mfa_logic(self, event):
        """Map MFA logic for Google Workspace."""
        event_name = event.get('name')
        if event_name in ['ENFORCE_STRONG_AUTHENTICATION', 'UNENFORCE_STRONG_AUTHENTICATION']:
            return {
                'type': 'MFA_UPDATE',
                'user': event.get('actor', {}).get('email'),
                'action': event_name
            }
        return None

    def parse_role_assignment(self, event):
        """Map role assignment logic for Google Workspace."""
        event_name = event.get('name')
        if event_name in ['ASSIGN_ROLE', 'REVOKE_ROLE']:
            return {
                'type': 'ROLE_ASSIGNMENT',
                'role': event.get('parameters', {}).get('ROLE_NAME'),
                'user': event.get('actor', {}).get('email'),
                'action': event_name
            }
        return None
