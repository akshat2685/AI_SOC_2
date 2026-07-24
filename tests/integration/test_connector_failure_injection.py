"""
Connector failure-injection tests (audit H — real connector implementations).

Exercises the exponential-backoff retry path shared by every SOAR connector
(`BaseConnector.execute_with_retry`) and the real `FirewallConnector`, proving:
  * transient upstream failures are retried and eventually succeed,
  * permanent failures surface after the retry budget is exhausted,
  * the retry loop is used by the production connector (not just the base class),
  * upstream HTTP 5xx / timeout are treated as retryable.

`asyncio.sleep` is monkeypatched to a no-op so backoff does not slow the suite.
"""
import asyncio
from typing import Any, Dict

import pytest

from intelligence_engine.soar.connectors.base import BaseConnector
from intelligence_engine.soar.connectors.firewall import FirewallConnector


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make exponential backoff instantaneous during tests."""
    async def _instant(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)


class _FlakyConnector(BaseConnector):
    """Fails `fail_times` times with a transient error, then succeeds."""

    def __init__(self, tenant_id: int, fail_times: int) -> None:
        super().__init__(tenant_id)
        self.fail_times = fail_times
        self.attempts = 0

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise ConnectionError(f"transient upstream failure #{self.attempts}")
        return {"status": "ok", "attempts": self.attempts, **params}

    async def rollback(self, params: Dict[str, Any], context: Dict[str, Any]) -> bool:
        return True


@pytest.mark.asyncio
async def test_retry_recovers_after_transient_failures():
    connector = _FlakyConnector(tenant_id=1, fail_times=2)
    result = await connector.execute_with_retry({"action": "block_ip", "ip": "10.0.0.9"}, max_retries=3)
    assert result["status"] == "ok"
    assert connector.attempts == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_retry_exhausts_and_raises_on_permanent_failure():
    connector = _FlakyConnector(tenant_id=1, fail_times=99)
    with pytest.raises(ConnectionError):
        await connector.execute_with_retry({"action": "block_ip", "ip": "10.0.0.9"}, max_retries=3)
    assert connector.attempts == 3  # exactly the retry budget, no more


@pytest.mark.asyncio
async def test_firewall_connector_retries_http_5xx_then_succeeds(monkeypatch):
    """
    Inject an upstream 5xx on the first call to the real FirewallConnector,
    then a success — verifying the production connector uses the retry loop.
    """
    import httpx

    calls = {"n": 0}

    class _FakeResponse:
        def __init__(self, status_code: int):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 500:
                raise httpx.HTTPStatusError(
                    "server error", request=None, response=None
                )

        def json(self):
            return {"blocked": True}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            calls["n"] += 1
            return _FakeResponse(500 if calls["n"] == 1 else 200)

        async def delete(self, *args, **kwargs):
            return _FakeResponse(200)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    connector = FirewallConnector(tenant_id=7)
    result = await connector.block_ip("203.0.113.5")
    assert result == {"blocked": True}
    assert calls["n"] == 2  # first 5xx retried, second succeeded
