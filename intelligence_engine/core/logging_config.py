import logging
import json
import contextvars
from datetime import datetime
from typing import Any, Dict

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
        if hasattr(record, "extra"):
            log_obj["extra"] = record.extra
        return json.dumps(log_obj)

def setup_logging(level: str = 'INFO'):
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
