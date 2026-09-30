"""Threat-intel ingest for the autonomous defense loop.

Daily pull of free feeds (CISA KEV, URLhaus; ThreatFox when a free
Auth-Key is configured) into the ``threat_intel_iocs`` table. The
detection engine reads the C2 sets via ``app.intel.refresh.get_c2_ips``
/ ``get_c2_domains``; the background loop lives in ``app.intel.loop``;
HTTP surface in ``app.intel.api``.

IoCs are GLOBAL, not tenant-scoped: the same malicious infrastructure
threatens every tenant.

Note: this __init__ deliberately stays light (model only) so that
importing app.domain.models — which re-exports ThreatIntelIoC for
alembic — never pulls httpx or the logger at import time.
"""

from app.intel.models import ThreatIntelIoC  # noqa: F401

__all__ = ["ThreatIntelIoC"]
