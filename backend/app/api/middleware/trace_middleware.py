import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.auth import current_trace_id

class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        token = current_trace_id.set(trace_id)
        request.state.trace_id = trace_id
        
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = trace_id
            return response
        finally:
            current_trace_id.reset(token)
