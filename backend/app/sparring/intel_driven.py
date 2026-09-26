"""Intel-driven attack scenarios: the twin attacks with REAL threat data.

Instead of only the 24 hardcoded simulated techniques, the twin pulls
fresh ammunition from the database every run:

1. **intel-ioc scenarios** — recent IoCs from the threat-intel feed
   (threat_intel_iocs): URLhaus malware IPs/domains/URLs, CISA KEV CVEs.
   Each becomes a concrete attack: a device connecting to the malicious
   IP, downloading from the malware URL, etc. This validates the
   intel -> detection path end-to-end: if a *known-bad* indicator evades,
   either the feed is stale or the rule is broken.

2. **alert-replay scenarios** — recent HIGH/CRITICAL alerts from the
   alerts table, rebuilt as anonymized event patterns on a virtual
   device. "Can we still catch last week's real attacks?" If a replay
   evades, the detection has regressed.

All scenarios are synthetic reconstructions scored in-memory by the real
engine. Nothing is written to tenant event tables; outcomes persist to
twin_scenarios for the learn step.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, select

logger = logging.getLogger(__name__)

TWIN_DEVICE_ID = "twin-virtual-device"

# Cap per run so the daily pass stays cheap.
MAX_IOC_SCENARIOS = 12
MAX_REPLAY_SCENARIOS = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_event(event_type: str) -> dict:
    return {
        "id": f"twin-{uuid.uuid4().hex[:8]}",
        "device_id": TWIN_DEVICE_ID,
        "event_type": event_type,
        "observed_at": _now_iso(),
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Source 1: threat-intel IoCs
# ---------------------------------------------------------------------------

async def build_ioc_scenarios(db, limit: int = MAX_IOC_SCENARIOS) -> list[dict]:
    """Build attack scenarios from the freshest intel IoCs.

    URLhaus IP   -> network connection to the malware-distribution IP
    URLhaus domain -> DNS/network connection to the malicious domain
    URLhaus URL  -> process downloads payload from URL, then executes it
    CISA KEV CVE -> simulated exploitation: vulnerable service spawns shell
    """
    scenarios: list[dict] = []
    try:
        from app.domain.models import ThreatIntelIoC

        rows = (
            (await db.execute(
                select(ThreatIntelIoC)
                .where(ThreatIntelIoC.ioc_type.in_(("ip", "domain", "url", "cve")))
                .order_by(desc(ThreatIntelIoC.updated_at))
                .limit(limit * 3)  # oversample; we pick a mix below
            ))
            .scalars().all()
        )
    except Exception:
        logger.exception("twin: failed to read intel IoCs")
        return []

    # Prefer a mix of types, freshest first.
    by_type: dict[str, list] = {"ip": [], "domain": [], "url": [], "cve": []}
    for r in rows:
        if r.ioc_type in by_type and r.value:
            by_type[r.ioc_type].append(r)

    per_type = max(1, limit // 4)
    for ioc_type in ("ip", "domain", "url", "cve"):
        for ioc in by_type[ioc_type][:per_type]:
            sc = _scenario_from_ioc(ioc)
            if sc:
                scenarios.append(sc)
            if len(scenarios) >= limit:
                break
        if len(scenarios) >= limit:
            break
    return scenarios


def _scenario_from_ioc(ioc) -> Optional[dict]:
    value = str(ioc.value or "").strip()
    if not value:
        return None
    malware = ioc.malware_family or "unknown malware"
    events: list[dict] = []

    if ioc.ioc_type == "ip":
        ev = _base_event("network")
        ev["network"] = {"dst_ip": value, "dst_port": 443, "protocol": "tcp"}
        events.append(ev)
        desc_text = (
            f"Device connects to {value}, a malware-distribution IP "
            f"({malware}) seen in the {ioc.source} feed."
        )
        technique, tactic = "T1071", "Command and Control"
    elif ioc.ioc_type == "domain":
        ev = _base_event("network")
        ev["network"] = {"dst_host": value.lower(), "dst_port": 443, "protocol": "tcp"}
        events.append(ev)
        desc_text = (
            f"Device connects to {value}, a malicious domain ({malware}) "
            f"seen in the {ioc.source} feed."
        )
        technique, tactic = "T1071", "Command and Control"
    elif ioc.ioc_type == "url":
        # Download + execute chain: the realistic shape of a URLhaus hit.
        dl = _base_event("network")
        host = value.split("/")[2] if "://" in value else value.split("/")[0]
        dl["network"] = {"dst_host": host.lower(), "dst_port": 80, "protocol": "tcp",
                         "url": value[:200]}
        exe = _base_event("process")
        exe["process"] = {"name": "payload.exe", "pid": 4242,
                          "exe": "C:\\Users\\victim\\Downloads\\payload.exe",
                          "cmdline": ["C:\\Users\\victim\\Downloads\\payload.exe"]}
        events.extend([dl, exe])
        desc_text = (
            f"Device downloads and executes a payload from {value[:80]} "
            f"({malware}, via {ioc.source})."
        )
        technique, tactic = "T1105", "Command and Control"
    elif ioc.ioc_type == "cve":
        # KEV CVE: simulate post-exploitation — a network service spawning
        # a shell is the canonical shape rules can actually see.
        ev = _base_event("process")
        ev["process"] = {"name": "cmd.exe", "pid": 1337,
                         "exe": "C:\\Windows\\System32\\cmd.exe",
                         "cmdline": ["cmd.exe", "/c", "whoami"],
                         "parent_name": "w3wp.exe"}
        events.append(ev)
        desc_text = (
            f"Simulated exploitation of {value} (CISA KEV): a web worker "
            f"process spawns a command shell."
        )
        technique, tactic = "T1190", "Initial Access"
    else:
        return None

    return {
        "scenario_id": f"ioc-{uuid.uuid4().hex[:8]}",
        "source": "intel-ioc",
        "technique_id": technique,
        "tactic": tactic,
        "description": desc_text,
        "ioc": {"source": ioc.source, "type": ioc.ioc_type, "value": value,
                "malware_family": malware, "threat_type": ioc.threat_type},
        "events": events,
        "simulated": True,
    }


# ---------------------------------------------------------------------------
# Source 2: replay of real past alerts
# ---------------------------------------------------------------------------

async def build_replay_scenarios(db, limit: int = MAX_REPLAY_SCENARIOS) -> list[dict]:
    """Rebuild recent HIGH/CRITICAL alerts as twin scenarios.

    Takes the alert's evidence and reconstructs the triggering event(s) on
    the virtual device, anonymized. Answers: "can we still catch the real
    attacks we saw last week?" A replay that evades means detection has
    regressed (rule changed, intel expired, threshold drifted).
    """
    scenarios: list[dict] = []
    try:
        from app.domain.models import Alert

        alerts = (
            (await db.execute(
                select(Alert)
                .where(Alert.severity.in_(("HIGH", "CRITICAL")))
                .where(Alert.rule_id.is_not(None))
                .order_by(desc(Alert.timestamp))
                .limit(limit * 2)
            ))
            .scalars().all()
        )
    except Exception:
        logger.exception("twin: failed to read alerts for replay")
        return []

    seen_rules: set[str] = set()
    for a in alerts:
        if a.rule_id in seen_rules:
            continue  # one replay per rule keeps the pass diverse
        sc = _scenario_from_alert(a)
        if sc:
            scenarios.append(sc)
            seen_rules.add(a.rule_id)
        if len(scenarios) >= limit:
            break
    return scenarios


def _scenario_from_alert(alert) -> Optional[dict]:
    ev = alert.evidence or {}
    rule_id = alert.rule_id or ""
    events: list[dict] = []

    if rule_id == "suspicious-cmdline":
        proc = ev.get("process") or {}
        e = _base_event("process")
        e["process"] = {
            "name": proc.get("name") or "evil.exe",
            "pid": 9001,
            "exe": proc.get("exe") or "C:\\temp\\evil.exe",
            "cmdline": proc.get("cmdline") or ["evil.exe", "sekurlsa::logonpasswords"],
        }
        events.append(e)
    elif rule_id in ("rare-outbound-port", "known-c2-connection",
                     "known-malicious-connection"):
        e = _base_event("network")
        e["network"] = {
            "dst_ip": ev.get("dst_ip") or "203.0.113.99",
            "dst_port": ev.get("dst_port") or 4444,
            "protocol": "tcp",
        }
        if ev.get("dst_host"):
            e["network"]["dst_host"] = ev["dst_host"]
        events.append(e)
    elif rule_id == "persistence-change":
        e = _base_event("persistence")
        e["persistence"] = {"path": ev.get("path") or "HKCU\\Run\\Updater"}
        events.append(e)
    elif rule_id == "brute-force-auth":
        for i in range(25):
            e = _base_event("auth")
            e["auth"] = {"result": "failed",
                         "username": (ev.get("usernames") or ["administrator"])[0]}
            events.append(e)
    else:
        return None  # no faithful reconstruction for this rule; skip honestly

    return {
        "scenario_id": f"replay-{uuid.uuid4().hex[:8]}",
        "source": "alert-replay",
        "technique_id": None,  # filled from the rule map at score time if known
        "tactic": None,
        "description": (
            f"Replay of real {alert.severity} alert #{alert.id} "
            f"({rule_id}): {str(alert.description or '')[:120]}"
        ),
        "replay_of_alert_id": alert.id,
        "rule_id": rule_id,
        "events": events,
        "simulated": True,
    }
