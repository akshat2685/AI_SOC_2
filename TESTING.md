# Testing Guide

## Running Tests Locally

### Execute Complete Suite
```bash
python -m pytest tests/ -v
```

### Coverage Report
```bash
python -m pytest tests/ --cov=backend/app --cov=intelligence_engine --cov-report=term-missing
```

## Test Structure
- `tests/api/`: REST API endpoints and rate limiter tests.
- `tests/unit/`: Error handling, detection engine, and Pydantic LLM output validation tests.
- `tests/integration/`: ClickHouse lock safety and async SOAR policy execution tests.
- `tests/security/`: Authentication and security boundaries tests.
- `tests/test_logging.py`: Structured JSON logger tests.
- `tests/test_migrations.py`: Alembic migration configuration tests.
