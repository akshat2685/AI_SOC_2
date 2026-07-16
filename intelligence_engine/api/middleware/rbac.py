from enum import Enum
from fastapi import HTTPException, Depends, status
from typing import Callable

from .auth import get_current_user

class Role(str, Enum):
    viewer = "viewer"
    analyst = "analyst"
    senior_analyst = "senior_analyst"
    admin = "admin"
    super_admin = "super_admin"

# Hierarchy defines that a higher value has access to lower value resources
ROLE_HIERARCHY = {
    Role.viewer: 1,
    Role.analyst: 2,
    Role.senior_analyst: 3,
    Role.admin: 4,
    Role.super_admin: 5,
}

def require_role(min_role: Role):
    """
    Decorator dependency to enforce Role-Based Access Control (RBAC).
    Checks if the current authenticated user has the necessary minimum role.
    """
    def role_dependency(user: dict = Depends(get_current_user)):
        user_role_str = user.get("role")
        if not user_role_str:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No role assigned to user."
            )
        
        try:
            user_role = Role(user_role_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid role: '{user_role_str}'."
            )

        if ROLE_HIERARCHY[user_role] < ROLE_HIERARCHY[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Minimum role required: {min_role.value}"
            )
        
        return user
    
    return role_dependency
