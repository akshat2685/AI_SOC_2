import logging
import traceback
from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler to catch unhandled errors and return a structured JSON response.
    """
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    
    # Try to get the trace_id from the request state if it was added by TraceMiddleware
    trace_id = getattr(request.state, "trace_id", "unknown")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal Server Error",
            "trace_id": trace_id,
            "message": str(exc)
        }
    )
