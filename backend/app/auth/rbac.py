"""Role-Based and Attribute-Based Access Control (RBAC/ABAC) module."""
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any


class Permission(Enum):
    """Enumeration of system permissions."""
    READ_ALERTS = "read_alerts"
    CREATE_INCIDENT = "create_incident"
    APPROVE_CRITICAL_ACTION = "approve_critical_action"
    MANAGE_USERS = "manage_users"
    MANAGE_SYSTEM = "manage_system"
    EXECUTE_CONTAINMENT = "execute_containment"
    VIEW_AUDIT_LOGS = "view_audit_logs"


ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "soc_analyst": {
        Permission.READ_ALERTS.value,
        Permission.CREATE_INCIDENT.value,
        Permission.EXECUTE_CONTAINMENT.value,
    },
    "analyst": {  # Legacy mapping
        Permission.READ_ALERTS.value,
        Permission.CREATE_INCIDENT.value,
        Permission.EXECUTE_CONTAINMENT.value,
    },
    "soc_manager": {
        Permission.READ_ALERTS.value,
        Permission.CREATE_INCIDENT.value,
        Permission.APPROVE_CRITICAL_ACTION.value,
        Permission.EXECUTE_CONTAINMENT.value,
        Permission.VIEW_AUDIT_LOGS.value,
    },
    "manager": {
        Permission.READ_ALERTS.value,
        Permission.CREATE_INCIDENT.value,
        Permission.APPROVE_CRITICAL_ACTION.value,
        Permission.EXECUTE_CONTAINMENT.value,
        Permission.VIEW_AUDIT_LOGS.value,
    },
    "admin": {p.value for p in Permission},
}


def get_permissions_for_role(role: str) -> Set[str]:
    """Retrieve all permission strings assigned to a specific role."""
    return ROLE_PERMISSIONS.get(role.lower(), set())


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a given permission."""
    if role.lower() == "admin":
        return True
    perms = get_permissions_for_role(role)
    return permission in perms


class ABACPolicy:
    """Attribute-Based Access Control policy evaluator."""

    def __init__(self):
        self._user_zone_restrictions: Dict[str, List[str]] = {}

    def set_zone_restrictions(self, user_id: str, zones: List[str]) -> None:
        """Set permitted security zones for a user."""
        self._user_zone_restrictions[user_id] = zones

    def can_access_resource(
        self, user_ctx: Dict[str, Any], resource_ctx: Dict[str, Any], permission: str
    ) -> Tuple[bool, str]:
        """Evaluate if user context can access resource context for a given permission."""
        user_id = user_ctx.get("user_id", "")
        role = user_ctx.get("role", "")

        # Step 1: RBAC check
        if not has_permission(role, permission):
            return False, f"RBAC denied: role '{role}' lacks permission '{permission}'"

        # Step 2: ABAC zone check
        if user_id in self._user_zone_restrictions:
            allowed_zones = self._user_zone_restrictions[user_id]
            resource_zone = resource_ctx.get("zone")
            if resource_zone and resource_zone not in allowed_zones:
                return False, f"ABAC access denied: zone '{resource_zone}' not in allowed zones {allowed_zones}"

        return True, "Allowed"


abac_policy = ABACPolicy()
