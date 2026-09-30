"""Fetchers for free threat-intel feeds.

Honest failure handling throughout: timeouts, HTTP errors, and malformed
payloads raise :class:`IntelSourceError` with a clear message. Fetchers
never invent IoCs — an empty feed or a dead source yields zero rows and
an error record, not synthetic data.

Feed notes (verified 2026-09-26):
- CISA KEV JSON moved from .../json/known_exploited_vulnerabilities.json
  (now 404) to .../feeds/known_exploited_vulnerabilities.json.
- ThreatFox API requires a free ``Auth-Key`` header since ~2025
  (https://auth.abuse.ch). Without ``THREATFOX_AUTH_KEY`` the fetcher
  raises instead of silently skipping.
- URLhaus csv_recent export still works without a key.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

KEV_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
THREATFOX_URL = "https://threatfox-api.abuse.ch/api/v1/"
URLHAUS_CSV_URL = "https://urlhaus.abuse.ch/downloads/csv_recent/"

MAX_IOCS_PER_SOURCE = 5000
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class IntelSourceError(Exception):
    """A feed could not be fetched or parsed. Never a data problem."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse the timestamp shapes the feeds actually emit; None on failure."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",  # ThreatFox / URLhaus
        "%Y-%m-%dT%H:%M:%S%z",  # ISO with offset
        "%Y-%m-%dT%H:%M:%S",  # ISO naive
        "%Y-%m-%d",  # KEV dateAdded
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _ioc(
    ioc_type: str,
    value: str,
    threat_type: Optional[str] = None,
    malware_family: Optional[str] = None,
    first_seen: Optional[datetime] = None,
    last_seen: Optional[datetime] = None,
    raw: Optional[dict] = None,
) -> dict:
    return {
        "ioc_type": ioc_type,
        "value": value,
        "threat_type": threat_type,
        "malware_family": malware_family,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "raw": raw,
    }


def fetch_cisa_kev() -> list[dict]:
    """Known Exploited Vulnerabilities: CVE ID + vendor/product + dateAdded."""
    try:
        resp = httpx.get(KEV_URL, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise IntelSourceError(f"cisa-kev fetch timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise IntelSourceError(f"cisa-kev HTTP error: {exc}") from exc
    try:
        data = resp.json()
    except ValueError as exc:
        raise IntelSourceError(f"cisa-kev returned non-JSON: {exc}") from exc

    vulns = data.get("vulnerabilities")
    if not isinstance(vulns, list):
        raise IntelSourceError("cisa-kev payload missing 'vulnerabilities' list")

    iocs: list[dict] = []
    for v in vulns[:MAX_IOCS_PER_SOURCE]:
        cve = str(v.get("cveID") or "").strip()
        if not cve:
            continue
        vendor = str(v.get("vendorProject") or "").strip()
        product = str(v.get("product") or "").strip()
        iocs.append(
            _ioc(
                ioc_type="cve",
                value=cve,
                threat_type="known-exploited-vulnerability",
                malware_family=None,
                first_seen=_parse_ts(v.get("dateAdded")),
                last_seen=None,  # KEV tracks addition date, not last sighting
                raw={
                    "vendor": vendor or None,
                    "product": product or None,
                    "name": v.get("vulnerabilityName"),
                    "dateAdded": v.get("dateAdded"),
                    "dueDate": v.get("dueDate"),
                    "knownRansomwareCampaignUse": v.get("knownRansomwareCampaignUse"),
                },
            )
        )
    return iocs


_THREATFOX_TYPE_MAP = {
    "ip:port": "ip",
    "domain": "domain",
    "url": "url",
    "md5_hash": "hash",
    "sha1_hash": "hash",
    "sha256_hash": "hash",
}


def _threatfox_value(ioc_type: str, raw_value: str) -> Optional[str]:
    """Normalize ThreatFox IOC strings: strip ports from ip:port entries."""
    if ioc_type == "ip:port":
        host = raw_value.rsplit(":", 1)[0].strip("[]")
        return host or None
    return raw_value.strip() or None


def fetch_threatfox(auth_key: Optional[str] = None) -> list[dict]:
    """Recent ThreatFox IOCs (last day). Requires a free abuse.ch Auth-Key."""
    if not auth_key:
        raise IntelSourceError(
            "threatfox needs a free Auth-Key from https://auth.abuse.ch "
            "(set the THREATFOX_AUTH_KEY environment variable); refusing to "
            "pretend the feed is empty"
        )
    try:
        resp = httpx.post(
            THREATFOX_URL,
            json={"query": "get_iocs", "days": 1},
            headers={"Auth-Key": auth_key},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise IntelSourceError(f"threatfox fetch timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise IntelSourceError(f"threatfox HTTP error: {exc}") from exc
    try:
        data = resp.json()
    except ValueError as exc:
        raise IntelSourceError(f"threatfox returned non-JSON: {exc}") from exc

    if data.get("query_status") != "ok":
        raise IntelSourceError(
            f"threatfox query failed: {data.get('query_status')!r}"
        )
    rows = data.get("data") or []
    if not isinstance(rows, list):
        raise IntelSourceError("threatfox payload 'data' is not a list")

    iocs: list[dict] = []
    for r in rows[:MAX_IOCS_PER_SOURCE]:
        raw_type = str(r.get("ioc_type") or "")
        norm_type = _THREATFOX_TYPE_MAP.get(raw_type)
        if not norm_type:
            continue  # unknown type: skip, never guess
        value = _threatfox_value(raw_type, str(r.get("ioc") or ""))
        if not value:
            continue
        malware = r.get("malware_printable") or r.get("malware") or None
        iocs.append(
            _ioc(
                ioc_type=norm_type,
                value=value,
                threat_type=str(r.get("threat_type") or "").strip() or None,
                malware_family=str(malware).strip() if malware else None,
                first_seen=_parse_ts(r.get("first_seen")),
                last_seen=_parse_ts(r.get("last_seen")),
                raw={
                    "threatfox_id": r.get("id"),
                    "confidence_level": r.get("confidence_level"),
                    "reporter": r.get("reporter"),
                    "reference": r.get("reference"),
                },
            )
        )
    return iocs


def _urlhaus_domain_ioc(url: str, threat: Optional[str], row: dict) -> Optional[dict]:
    """Derive a domain (or ip) IoC from a URLhaus URL. Derivation, not invention."""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return None
    host = host.strip().lower().rstrip(".")
    if not host:
        return None
    # IP-literal host -> ip IoC; otherwise domain IoC.
    try:
        import ipaddress

        ipaddress.ip_address(host)
        ioc_type = "ip"
    except ValueError:
        ioc_type = "domain"
    return _ioc(
        ioc_type=ioc_type,
        value=host,
        threat_type=threat,
        malware_family=None,
        first_seen=_parse_ts(row.get("dateadded")),
        last_seen=_parse_ts(row.get("last_online")),
        raw={"derived_from_url": url, "urlhaus_id": row.get("id")},
    )


def fetch_urlhaus() -> list[dict]:
    """URLhaus recent-malware-URL CSV dump (keyless). Emits url + derived domain/ip IoCs."""
    try:
        resp = httpx.get(URLHAUS_CSV_URL, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise IntelSourceError(f"urlhaus fetch timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise IntelSourceError(f"urlhaus HTTP error: {exc}") from exc

    text = resp.text
    # The CSV's comment block includes the header line as "# id,dateadded,...".
    # Recover it as the real header instead of dropping it (dropping it makes
    # DictReader treat the first data row as the header and match nothing).
    header: Optional[str] = None
    data_lines: list[str] = []
    for ln in text.splitlines():
        if not ln.strip():
            continue
        if ln.startswith("#"):
            if ln.startswith("# id,"):
                header = ln.lstrip("#").strip()
            continue
        data_lines.append(ln)
    if header is None or not data_lines:
        raise IntelSourceError("urlhaus CSV had no usable header/data rows")

    iocs: list[dict] = []
    reader = csv.DictReader([header] + data_lines)
    for row in reader:
        if len(iocs) >= MAX_IOCS_PER_SOURCE:
            break
        url = (row.get("url") or "").strip()
        if not url:
            continue
        threat = (row.get("threat") or "").strip() or None
        iocs.append(
            _ioc(
                ioc_type="url",
                value=url,
                threat_type=threat,
                malware_family=None,
                first_seen=_parse_ts(row.get("dateadded")),
                last_seen=_parse_ts(row.get("last_online")),
                raw={
                    "urlhaus_id": row.get("id"),
                    "url_status": row.get("url_status"),
                    "reporter": row.get("reporter"),
                },
            )
        )
        domain_ioc = _urlhaus_domain_ioc(url, threat, row)
        if domain_ioc and len(iocs) < MAX_IOCS_PER_SOURCE:
            iocs.append(domain_ioc)
    return iocs
