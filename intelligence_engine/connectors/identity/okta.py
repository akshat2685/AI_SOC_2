class OktaConnector:
    def __init__(self, domain, api_token):
        self.domain = domain
        self.api_token = api_token

    def parse_mfa_logic(self, event):
        """Map MFA logic for Okta."""
        event_type = event.get('eventType')
        if event_type in ['user.mfa.factor.activate', 'user.mfa.factor.deactivate']:
            return {
                'type': 'MFA_UPDATE',
                'user': event.get('actor', {}).get('alternateId'),
                'action': event_type
            }
        return None

    def parse_role_assignment(self, event):
        """Map role assignment logic for Okta."""
        event_type = event.get('eventType')
        if event_type in ['user.account.privilege.grant', 'user.account.privilege.revoke']:
            return {
                'type': 'ROLE_ASSIGNMENT',
                'role': event.get('target', [{}])[0].get('displayName'),
                'user': event.get('actor', {}).get('alternateId'),
                'action': event_type
            }
        return None
