import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.auth import current_tenant_id, current_user_id, current_trace_id
from app.application.audit_logger import audit_logger

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
            return await call_next(request)
            
        start_time = time.time()
        
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise e
        finally:
            duration = time.time() - start_time
            tenant_id = current_tenant_id.get()
            
            if tenant_id:
                audit_logger.emit(
                    action=f"http_{request.method.lower()}",
                    tenant_id=tenant_id,
                    user_id=current_user_id.get(),
                    trace_id=current_trace_id.get(),
                    details={
                        "path": request.url.path,
                        "method": request.method,
                        "status_code": status_code,
                        "duration_ms": int(duration * 1000),
                        "client_ip": request.client.host if request.client else None
                    }
                )
                
        return response
