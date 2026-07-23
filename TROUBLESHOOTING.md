# Troubleshooting Guide

## Common Issues & Solutions

### 1. `RuntimeError: Required environment variable GEMINI_API_KEY is not set`
**Cause**: `GEMINI_API_KEY` is missing from system environment or `.env` file.
**Fix**: Ensure `GEMINI_API_KEY` is defined in `.env` or set in terminal: `export GEMINI_API_KEY="your_api_key"`.

### 2. SlowAPI `429 Too Many Requests`
**Cause**: Endpoint request rate exceeded configured limit.
**Fix**: Adjust rate limit settings or wait 60 seconds for rate limit window reset.

### 3. ClickHouse Connection Failures
**Cause**: ClickHouse server not running or network blocked.
**Fix**: Verify ClickHouse status via `docker compose ps` or check `CLICKHOUSE_HOST` host settings.
