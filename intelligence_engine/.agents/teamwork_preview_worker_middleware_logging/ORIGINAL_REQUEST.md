## 2026-07-15T14:19:15Z
You are teamwork_preview_worker_middleware_logging.
Your working directory is C:\Users\ijain\AI_SOC_2\intelligence_engine\.agents\teamwork_preview_worker_middleware_logging.
Your parent conversation ID is 0ce7f15d-4bac-4814-a96b-276053bb69a2.

Your mission is to execute Milestone 7 (Middleware Stack & Logger Integration) in C:\Users\ijain\AI_SOC_2\intelligence_engine.
Specifically:
1. Inspect C:\Users\ijain\AI_SOC_2\intelligence_engine\core\logging_config.py to understand how trace_id context variable (trace_id_var) and JSONFormatter are defined.
2. Create api/middleware directory if it doesn't exist, and create middleware scripts (e.g. api/middleware/trace_middleware.py or similar).
3. Implement a middleware stack that:
   - Injects/extracts a unique trace ID (Request ID) for every incoming request. Check headers like X-Request-ID or X-Trace-ID. If not found, generate a UUID.
   - Sets the trace ID in the contextvars.ContextVar (trace_id_var from core/logging_config.py) so all logs generated during the request lifecycle automatically include it.
   - Adds the trace ID to the response headers (e.g., X-Request-ID).
   - Catches all global unhandled exceptions, logs them with trace ID, and returns a standard JSON error response (e.g., status 500: {"detail": "Internal server error", "trace_id": "..."}).
   - Logs the request (method, path, client IP) and response status/latency.
4. Mount this middleware stack on the FastAPI application in api/main.py. Ensure that logging is set up on app startup using core/logging_config.py:setup_logging().
5. Update tests/test_main_api.py to add tests verifying:
   - Incoming request triggers trace ID generation.
   - Response header contains X-Request-ID.
   - Global exception handler is triggered on exceptions and returns a JSON structure with trace_id.
   - Logs output contains the trace_id.
6. Write your handoff report to handoff.md in your working directory and send a message back to the parent.
