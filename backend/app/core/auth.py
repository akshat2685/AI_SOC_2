from contextvars import ContextVar
from typing import Optional

# Context variable to store the current tenant_id for RLS and auditing
current_tenant_id: ContextVar[Optional[int]] = ContextVar("current_tenant_id", default=None)
current_user_id: ContextVar[Optional[int]] = ContextVar("current_user_id", default=None)
current_api_key: ContextVar[Optional[str]] = ContextVar("current_api_key", default=None)
current_trace_id: ContextVar[Optional[str]] = ContextVar("current_trace_id", default=None)
