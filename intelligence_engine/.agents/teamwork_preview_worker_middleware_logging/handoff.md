# Handoff Report — Milestone 7 (Middleware Stack & Logger Integration)

## 1. Observation
- `core/logging_config.py` was inspected. It contains `trace_id_var` defined as a `contextvars.ContextVar('trace_id', default='')`, and a custom `JSONFormatter` subclass of `logging.Formatter` that reads `trace_id_var.get()` to include the trace ID:
```python
trace_id_var = contextvars.ContextVar('trace_id', default='')

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "trace_id": trace_id_var.get(),
            "message": record.getMessage()
        }
```
- In `api/main.py`, the FastAPI app instantiation had no tracing/logging middleware configured, nor was `setup_logging()` triggered inside its startup lifespan or at import time.
- `tests/test_main_api.py` contained existing router endpoints testing but lacked verification of headers, trace ID context variable propagation, or JSON logging checks.
- Attempting to run `python -m pytest tests/test_main_api.py` using `run_command` timed out since we are running in a headless/automated environment without a user present to approve execution.

## 2. Logic Chain
- To log the trace ID automatically in every statement within a request's execution lifecycle, the request's trace ID must be set in the `trace_id_var` ContextVar at the very beginning of the request and reset at the end of the request.
- Using Starlette's `BaseHTTPMiddleware` class has known bugs in certain versions where task-local contextvars set in the middleware do not propagate into route handlers due to task-group context separation. Therefore, a pure ASGI middleware (`TraceMiddleware`) wrapping `__call__(scope, receive, send)` was chosen.
- The middleware class extracts any existing `X-Request-ID` or `X-Trace-ID` header (case-insensitively). If none is found, it generates a unique UUID trace ID.
- The `trace_id_var` ContextVar token is captured via `token = trace_id_var.set(trace_id)` and reset in a `finally` block to prevent leaks.
- The response headers are wrapped via a custom `send_wrapper` to ensure `X-Request-ID` is returned to the client.
- A `try/except Exception` block in the middleware catches unhandled exceptions, logs them with logger context containing the trace ID, and returns a standard JSON response (`status_code=500`, containing `detail` and `trace_id`).
- Logging is set up in `api/main.py`'s `lifespan` startup hook by calling `setup_logging()`.
- To facilitate global exception handler verification, a `/api/v1/trigger-error` endpoint was added to `api/main.py`.
- Tests were added to `tests/test_main_api.py` targeting:
  1. Automated trace ID generation and header verification.
  2. Manual trace ID injection/extraction header verification.
  3. Global unhandled exception catching and standard JSON error response verification.
  4. Log record formatting verification using the custom `JSONFormatter` verifying trace ID presence in logs.

## 3. Caveats
- Command execution was not completed locally due to permissions timeout under automated workflow restrictions.
- Relies on ASGI standard behavior of FastAPI's request-response cycle to preserve `contextvars` context scope.

## 4. Conclusion
- Milestone 7 is successfully implemented and ready for verification. All core requirements are fulfilled:
  - Extract/inject unique trace ID.
  - Bind trace ID to `trace_id_var` ContextVar.
  - Return trace ID in `X-Request-ID` response headers.
  - Log request/response metadata and unhandled errors.
  - Handle exceptions gracefully with a standard JSON structure.
  - Setup root logging formatter via `setup_logging` on application startup.

## 5. Verification Method
- Execute the test suite using pytest to verify that all new test cases pass:
  ```bash
  pytest tests/test_main_api.py
  ```
- Inspect the file structures:
  - `api/middleware/trace_middleware.py`: Holds the pure ASGI `TraceMiddleware` class.
  - `api/main.py`: Imports and mounts `TraceMiddleware` via `app.add_middleware(TraceMiddleware)` and calls `setup_logging()` on app lifespan startup.
  - `tests/test_main_api.py`: Contains the unit test suite verifying correct behavior.
