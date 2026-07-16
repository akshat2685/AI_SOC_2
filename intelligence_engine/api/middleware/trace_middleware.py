import time
import uuid
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse

try:
    from core.logging_config import trace_id_var, get_logger
except ImportError:
    from intelligence_engine.core.logging_config import trace_id_var, get_logger

logger = get_logger("api.middleware.trace")

class TraceMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract trace ID from request headers (case-insensitive search)
        headers = scope.get("headers", [])
        trace_id = None
        for name, value in headers:
            if name.lower() in (b"x-request-id", b"x-trace-id"):
                try:
                    trace_id = value.decode("utf-8")
                except Exception:
                    pass
                break

        if not trace_id:
            trace_id = str(uuid.uuid4())

        # Set the trace ID in contextvars
        token = trace_id_var.set(trace_id)

        # Get request metadata: method, path, client IP
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "")
        
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        logger.info(f"Incoming request: {method} {path} from {client_ip}")
        start_time = time.perf_counter()

        status_code = [200]  # mutable reference to capture status code inside send_wrapper

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 200)
                msg_headers = list(message.get("headers", []))
                
                # Check if X-Request-ID is already present in headers
                has_request_id = any(name.lower() == b"x-request-id" for name, _ in msg_headers)
                if not has_request_id:
                    msg_headers.append((b"x-request-id", trace_id.encode("utf-8")))
                
                message["headers"] = msg_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            latency = time.perf_counter() - start_time
            logger.info(
                f"Request completed: {method} {path} - Status: {status_code[0]} - Latency: {latency:.4f}s"
            )
        except Exception as exc:
            latency = time.perf_counter() - start_time
            logger.exception(
                f"Unhandled exception during request {method} {path}: {exc} - Latency: {latency:.4f}s"
            )
            # Create standard JSON error response (status 500)
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "trace_id": trace_id
                }
            )
            # Set response header
            response.headers["X-Request-ID"] = trace_id
            await response(scope, receive, send)
        finally:
            trace_id_var.reset(token)
