# Observability & Monitoring Setup

## Prometheus Metrics
Metrics are exposed on the application observability endpoint:
- `kafka_consumer_lag`: Consumer group partition lag.
- `clickhouse_flush_latency_seconds`: ClickHouse batch write duration.
- `dlq_events_total`: Total count of events routed to Dead Letter Queue.

## Structured JSON Logs
All logs follow ISO-8601 UTC JSON format:
```json
{
  "timestamp": "2026-07-23T15:20:00.000Z",
  "level": "info",
  "name": "intelligence_engine.agents.soc_orchestrator",
  "message": "orchestrator_started",
  "alert_id": "ALT-1001",
  "hitl_level": 1
}
```
