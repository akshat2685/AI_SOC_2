import time
import hashlib
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.auth import current_tenant_id, current_user_id, current_trace_id
from app.application.audit_logger import audit_logger

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
            return await call_next(request)
            
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        request_id = request.headers.get("x-request-id", current_trace_id.get())
        
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise e
        finally:
            duration = time.time() - start_time
            duration_ms = int(duration * 1000)
            tenant_id = current_tenant_id.get()
            
            if tenant_id:
                details = {
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "request_id": request_id,
                }
                
                audit_logger.emit(
                    action=f"http_{request.method.lower()}",
                    tenant_id=tenant_id,
                    user_id=current_user_id.get(),
                    trace_id=request_id,
                    details=details
                )
                
        return response
