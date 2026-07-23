import json
import logging
import pytest
import structlog
from backend.app.core.logger import setup_logging

def test_structured_logging_configuration():
    """Verify structlog configuration produces loggers without exception."""
    setup_logging(log_level="DEBUG")
    logger = structlog.get_logger("test_logger")
    assert logger is not None

def test_logger_methods_callable():
    """Verify standard structlog log level methods execute."""
    logger = structlog.get_logger("test_logger")
    logger.info("test_info_event", alert_id="ALT-1234", tenant_id=1)
    logger.warning("test_warning_event", count=5)
    logger.error("test_error_event", error="simulated_error")
