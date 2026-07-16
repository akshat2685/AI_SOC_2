"""Wazuh SIEM connector — async HTTP integration via the Wazuh REST API."""

import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

import httpx

from intelligence_engine.connectors.base import BaseConnector, SecurityEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wazuh rule-group → MITRE ATT&CK technique mapping (common subset)
# ---------------------------------------------------------------------------
_RULE_GROUP_TO_MITRE: dict[str, list[str]] = {
    "authentication_failed": ["T1110"],       # Brute Force
    "authentication_success": ["T1078"],      # Valid Accounts
    "syslog": ["T1070.002"],                  # Indicator Removal: Clear Linux Logs
    "web_scan": ["T1595"],                    # Active Scanning
    "exploit_attempt": ["T1190"],             # Exploit Public-Facing Application
    "rootkit": ["T1014"],                     # Rootkit
    "trojan": ["T1204"],                      # User Execution
    "virus": ["T1204.002"],                   # Malicious File
    "windows": ["T1059.001"],                 # PowerShell
    "firewall_drop": ["T1571"],               # Non-Standard Port
    "ids": ["T1046"],                         # Network Service Discovery
    "ossec": ["T1562.001"],                   # Disable or Modify Tools
    "sshd": ["T1021.004"],                    # Remote Services: SSH
    "pam": ["T1556"],                         # Modify Authentication Process
    "local_anomaly": ["T1547"],               # Boot or Logon Autostart
    "web_attack": ["T1190"],                  # Exploit Public-Facing App
    "sql_injection": ["T1190"],               # Exploit Public-Facing App
    "xss": ["T1189"],                         # Drive-by Compromise
    "reconnaissance": ["T1592"],              # Gather Victim Host Information
    "lateral_movement": ["T1021"],            # Remote Services
    "privilege_escalation": ["T1068"],        # Exploitation for Privilege Escalation
}

# Regex patterns for IOC extraction
_IOC_PATTERNS: dict[str, re.Pattern] = {
    "ipv4": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|1?\d\d?)\b"
    ),
    "md5": re.compile(r"\b[a-fA-F0-9]{32}\b"),
    "sha256": re.compile(r"\b[a-fA-F0-9]{64}\b"),
    "domain": re.compile(
        r"\b(?:[a-zA-Z0-9-]+\.)+(?:com|net|org|io|ru|cn|xyz|tk|top|info|biz)\b"
    ),
    "url": re.compile(r"https?://[^\s\"'<>]+"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
}

# Private / reserved IPs to skip when extracting IOCs
_PRIVATE_IP = re.compile(
    r"^(?:127\.|10\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.)"
)


def _severity_from_level(level: int) -> str:
    """Map Wazuh numeric rule level to canonical severity string."""
    if level >= 12:
        return "CRITICAL"
    if level >= 8:
        return "HIGH"
    if level >= 4:
        return "MEDIUM"
    return "LOW"


class WazuhConnector(BaseConnector):
    """Async connector for the Wazuh SIEM REST API.

    Configuration is read from environment variables:
        WAZUH_API_URL   – e.g. https://wazuh-manager:55000
        WAZUH_USER      – API user (default: wazuh-wui)
        WAZUH_PASSWORD   – API password
        WAZUH_TENANT_ID – tenant identifier (default: "default")
        WAZUH_VERIFY_SSL – set to "false" to skip TLS verification
    """

    def __init__(self) -> None:
        self._api_url = os.getenv("WAZUH_API_URL", "https://localhost:55000")
        self._user = os.getenv("WAZUH_USER", "wazuh-wui")
        self._password = os.getenv("WAZUH_PASSWORD", "")
        self._tenant_id = os.getenv("WAZUH_TENANT_ID", "default")
        self._verify_ssl = os.getenv("WAZUH_VERIFY_SSL", "true").lower() != "false"

        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._last_sync: datetime | None = None
        self._acknowledged: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create a persistent async HTTP client."""
        logger.info("Connecting to Wazuh API at %s", self._api_url)
        self._client = httpx.AsyncClient(
            base_url=self._api_url,
            verify=self._verify_ssl,
            timeout=httpx.Timeout(30.0),
        )

    async def authenticate(self) -> None:
        """Obtain a JWT from the Wazuh /security/user/authenticate endpoint."""
        if self._client is None:
            raise RuntimeError("Call connect() before authenticate()")

        logger.info("Authenticating with Wazuh as user '%s'", self._user)
        try:
            resp = await self._client.post(
                "/security/user/authenticate",
                auth=(self._user, self._password),
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("data", {}).get("token")
            if not self._token:
                raise ValueError("Authentication response missing token")
            self._client.headers["Authorization"] = f"Bearer {self._token}"
            logger.info("Wazuh authentication successful")
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Wazuh auth failed – HTTP %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise
        except httpx.RequestError as exc:
            logger.error("Wazuh auth request error: %s", exc)
            raise

    async def health(self) -> dict:
        """Ping the Wazuh API and report connector health."""
        if self._client is None:
            return {
                "status": "unhealthy",
                "latency_ms": -1,
                "last_sync": None,
            }

        start = time.monotonic()
        try:
            resp = await self._client.get("/")
            resp.raise_for_status()
            latency = round((time.monotonic() - start) * 1000, 2)
            return {
                "status": "healthy",
                "latency_ms": latency,
                "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            }
        except Exception as exc:
            latency = round((time.monotonic() - start) * 1000, 2)
            logger.warning("Wazuh health check failed: %s", exc)
            return {
                "status": "unhealthy",
                "latency_ms": latency,
                "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            }

    async def fetch_events(self, since: datetime) -> list[dict]:
        """Retrieve alerts from Wazuh created after *since*."""
        if self._client is None:
            raise RuntimeError("Call connect() before fetch_events()")

        since_str = since.strftime("%Y-%m-%dT%H:%M:%S+0000")
        all_alerts: list[dict] = []
        offset = 0
        limit = 500

        while True:
            try:
                resp = await self._client.get(
                    "/alerts",
                    params={
                        "offset": offset,
                        "limit": limit,
                        "sort": "+timestamp",
                        "q": f"timestamp>{since_str}",
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                items = body.get("data", {}).get("affected_items", [])
                if not items:
                    break
                all_alerts.extend(items)
                total = body.get("data", {}).get("total_affected_items", 0)
                offset += limit
                if offset >= total:
                    break
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Wazuh fetch_events HTTP %s: %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                break
            except httpx.RequestError as exc:
                logger.error("Wazuh fetch_events request error: %s", exc)
                break

        self._last_sync = datetime.now(tz=timezone.utc)
        logger.info("Fetched %d Wazuh alerts since %s", len(all_alerts), since_str)
        return all_alerts

    async def normalize(self, event: dict) -> SecurityEvent:
        """Convert a raw Wazuh alert dict into a canonical SecurityEvent."""
        rule = event.get("rule", {})
        level = int(rule.get("level", 0))
        groups = rule.get("groups", [])

        # Map rule groups to MITRE techniques
        mitre: list[str] = []
        for group in groups:
            mitre.extend(_RULE_GROUP_TO_MITRE.get(group.lower(), []))
        # De-duplicate while preserving order
        mitre = list(dict.fromkeys(mitre))

        # Extract IOCs from the full event payload
        iocs = self._extract_iocs(event)

        # Build normalized payload
        agent_info = event.get("agent", {})
        normalized_payload = {
            "rule_id": rule.get("id"),
            "rule_description": rule.get("description", ""),
            "rule_groups": groups,
            "rule_level": level,
            "agent_id": agent_info.get("id"),
            "agent_name": agent_info.get("name"),
            "agent_ip": agent_info.get("ip"),
            "manager_name": event.get("manager", {}).get("name"),
            "full_log": event.get("full_log", ""),
            "decoder_name": event.get("decoder", {}).get("name"),
            "location": event.get("location", ""),
        }

        # Parse timestamp
        ts_raw = event.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            ts = datetime.now(tz=timezone.utc)

        return SecurityEvent(
            event_id=event.get("id", str(uuid.uuid4())),
            tenant_id=self._tenant_id,
            source="wazuh",
            event_type=rule.get("description", "unknown"),
            severity=_severity_from_level(level),
            timestamp=ts,
            raw_payload=event,
            normalized_payload=normalized_payload,
            iocs=iocs,
            mitre_techniques=mitre,
        )

    async def acknowledge(self, event_ids: list[str]) -> None:
        """Mark event IDs as processed.

        Wazuh's REST API does not natively support ack; we track state
        locally so callers can avoid re-processing.
        """
        self._acknowledged.update(event_ids)
        logger.info("Acknowledged %d Wazuh events", len(event_ids))

    async def disconnect(self) -> None:
        """Close the HTTP client and invalidate the token."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._token = None
        logger.info("Disconnected from Wazuh API")

    # ------------------------------------------------------------------
    # IOC extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_iocs(event: dict) -> list[str]:
        """Walk the event dict and pull out IOC-like strings."""
        text = _flatten_to_text(event)
        iocs: list[str] = []

        for label, pattern in _IOC_PATTERNS.items():
            for match in pattern.finditer(text):
                value = match.group(0)
                # Skip private/reserved IPs
                if label == "ipv4" and _PRIVATE_IP.match(value):
                    continue
                if value not in iocs:
                    iocs.append(value)
        return iocs


def _flatten_to_text(obj: object, _parts: list[str] | None = None) -> str:
    """Recursively flatten a nested dict/list into a single text blob."""
    if _parts is None:
        _parts = []
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten_to_text(v, _parts)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_to_text(v, _parts)
    elif isinstance(obj, str):
        _parts.append(obj)
    return " ".join(_parts)
