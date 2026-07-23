import structlog
import json
import logging
import contextvars
from datetime import datetime
from typing import Any, Dict

trace_id_var = contextvars.ContextVar('trace_id', default='')

# Keep stdout logging bridge for structlog chain-of-responsibility
def setup_logging(level: str = 'INFO'):
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
