class AzureIAMConnector:
    def __init__(self, tenant_id, credentials):
        self.tenant_id = tenant_id
        self.credentials = credentials

    def parse_mfa_logic(self, event):
        """Map MFA logic for Azure IAM."""
        # Azure AD audit logs
        activity = event.get('activityDisplayName')
        if activity in ['Enable Strong Authentication', 'Disable Strong Authentication']:
            return {
                'type': 'MFA_UPDATE',
                'user': event.get('targetResources', [{}])[0].get('userPrincipalName'),
                'action': activity
            }
        return None

    def parse_role_assignment(self, event):
        """Map role assignment logic for Azure IAM."""
        activity = event.get('activityDisplayName')
        if activity in ['Add member to role', 'Remove member from role']:
            return {
                'type': 'ROLE_ASSIGNMENT',
                'role': event.get('modifiedProperties', {}).get('Role.DisplayName'),
                'user': event.get('targetResources', [{}])[0].get('userPrincipalName'),
                'action': activity
            }
        return None
