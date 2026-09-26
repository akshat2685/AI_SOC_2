"""Phase 2 detection rules (rules-v1).

Pure functions over plain event dicts — no database access, so they are
unit-testable without any infrastructure. The engine (engine.py) handles
fetching events, dedup, persistence, and correlation.

Event dict shape (from security_events rows):
    {
        "event_type": "process" | "network" | "file" | "auth" | "dns",
        "device_id": str,
        "observed_at": datetime,
        "severity_hint": str,
        "payload": { ... typed section ... },
    }

A finding is a plain dict:
    {
        "rule_id": str,            # stable id, e.g. "suspicious-cmdline"
        "rule_name": str,          # human title
        "severity": "LOW"|"MEDIUM"|"HIGH"|"CRITICAL",
        "confidence": int,         # 0-100, honest: rule confidence, not ML
        "title": str,
        "description": str,
        "fingerprint": str,        # stable dedup key
        "evidence": dict,          # raw details for the analyst
    }

Nothing here claims ML provenance. Rule findings are labeled
detector="rules-v1" by the engine.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import datetime

RULES_VERSION = "rules-v1"

# (regex, human description) — matched against the joined cmdline, case-insensitive.
_SUSPICIOUS_CMDLINE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"powershell.*-(e(nc(odedcommand)?)?|w\s+hidden|noprofile)", re.I),
     "PowerShell with encoded command or hidden window"),
    (re.compile(r"\bmimikatz\b", re.I), "Mimikatz credential dumper"),
    (re.compile(r"\bpsexec\b", re.I), "PsExec remote execution tool"),
    (re.compile(r"wmic\s+.*process\s+call\s+create", re.I), "WMIC remote process creation"),
    (re.compile(r"vssadmin\s+delete\s+shadows", re.I), "Volume shadow copy deletion (ransomware behavior)"),
    (re.compile(r"bcdedit.*recoveryenabled\s+no", re.I), "Boot recovery disabled"),
    (re.compile(r"ntdsutil", re.I), "NTDS database access attempt"),
    (re.compile(r"reg\s+save\s+hklm\\(sam|system|security)", re.I), "Registry hive exfiltration (SAM/SYSTEM/SECURITY)"),
    (re.compile(r"certutil\s+.*-decode", re.I), "CertUtil used to decode a payload (living-off-the-land)"),
    (re.compile(r"bitsadmin\s+.*transfer", re.I), "BITSAdmin used for download (living-off-the-land)"),
    (re.compile(r"rundll32.*\.dll.*,.*#\d+", re.I), "Rundll32 executing DLL export by ordinal"),
    (re.compile(r"mshta\s+http", re.I), "Mshta fetching remote payload"),
    (re.compile(r"wscript|cscript.*\.vbs.*http", re.I), "Script host with remote VBS"),
    (re.compile(r"net\s+user\s+\S+\s+\S+\s+/add", re.I), "Local user account creation via net.exe"),
    (re.compile(r"sekurlsa|lsadump", re.I), "LSASS memory dumping tooling"),
]

# Persistence registry markers (sensor reports Run-key changes as file events).
_PERSISTENCE_MARKERS = (
    "currentversion\\run",
    "currentversion\\runonce",
    "currentversion\\runservices",
)

# Ports that are normal for outbound client traffic; anything else public is notable.
_COMMON_OUTBOUND_PORTS = {80, 443, 53, 123, 993, 995, 587, 465, 22, 21, 25, 110, 143, 3389}


def _section(event: dict) -> dict:
    """Return the typed section of an event.

    The ingest API stores the typed section unwrapped (payload IS the
    section), while the raw sensor record nests it under its type key.
    Handle both shapes defensively.
    """
    payload = event.get("payload") or {}
    key = {
        "process": "process", "network": "network", "file": "file",
        "auth": "auth", "dns": "dns",
    }.get(str(event.get("event_type") or ""))
    if key and isinstance(payload.get(key), dict):
        return payload[key]
    return payload if isinstance(payload, dict) else {}


def _fingerprint(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()
    return h[:16]


def _is_public_ip(ip: str) -> bool | None:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_loopback or addr.is_private or addr.is_multicast or addr.is_reserved:
        return False
    return True


def _rule_suspicious_cmdline(event: dict) -> dict | None:
    if event.get("event_type") != "process":
        return None
    proc = _section(event)
    cmdline = proc.get("cmdline") or []
    joined = " ".join(cmdline) if isinstance(cmdline, list) else str(cmdline)
    if not joined:
        return None
    for pattern, description in _SUSPICIOUS_CMDLINE:
        if pattern.search(joined):
            name = proc.get("name") or "unknown process"
            return {
                "rule_id": "suspicious-cmdline",
                "rule_name": "Suspicious command line",
                "severity": "HIGH",
                "confidence": 85,
                "title": f"Suspicious command line: {name}",
                "description": f"{description} observed on device {event.get('device_id')}. "
                               f"Command: {joined[:300]}",
                "fingerprint": _fingerprint("suspicious-cmdline", event.get("device_id", ""),
                                            pattern.pattern, name),
                "evidence": {"cmdline": joined[:1000], "process": {k: proc.get(k) for k in
                              ("pid", "ppid", "name", "exe", "user", "hash_sha256")},
                             "matched": description},
            }
    return None


def _rule_persistence_change(event: dict) -> dict | None:
    if event.get("event_type") != "file":
        return None
    f = _section(event)
    path = str(f.get("path") or "")
    action = str(f.get("action") or "")
    if action not in ("created", "modified"):
        return None
    lowered = path.lower()
    if not any(m in lowered for m in _PERSISTENCE_MARKERS):
        return None
    return {
        "rule_id": "persistence-change",
        "rule_name": "Autorun persistence change",
        "severity": "HIGH",
        "confidence": 90,
        "title": f"Autorun registry value {action}: {path.split(chr(92))[-1]}",
        "description": f"A Run-key persistence value was {action} on device {event.get('device_id')}: {path}. "
                       f"New persistence mechanisms are high-interest until reviewed.",
        "fingerprint": _fingerprint("persistence-change", event.get("device_id", ""), path),
        "evidence": {"path": path, "action": action},
    }


def _rule_rare_outbound_port(event: dict) -> dict | None:
    if event.get("event_type") != "network":
        return None
    n = _section(event)
    dst_ip = str(n.get("dst_ip") or "")
    try:
        dst_port = int(n.get("dst_port") or 0)
    except (TypeError, ValueError):
        return None
    if not dst_ip or dst_port in _COMMON_OUTBOUND_PORTS:
        return None
    if _is_public_ip(dst_ip) is not True:
        return None
    proc = n.get("process_name") or "unknown process"
    return {
        "rule_id": "rare-outbound-port",
        "rule_name": "Outbound connection on uncommon port",
        "severity": "MEDIUM",
        "confidence": 60,
        "title": f"Outbound to {dst_ip}:{dst_port} ({proc})",
        "description": f"Device {event.get('device_id')} opened an outbound connection to public "
                       f"{dst_ip}:{dst_port} via {proc}. Uncommon ports can indicate C2 or tunneling.",
        "fingerprint": _fingerprint("rare-outbound-port", event.get("device_id", ""), dst_ip, str(dst_port)),
        "evidence": {"dst_ip": dst_ip, "dst_port": dst_port, "proto": n.get("proto"),
                     "process_name": proc, "pid": n.get("pid")},
    }


def _rule_first_seen_binary(event: dict, known_hashes: set[str]) -> dict | None:
    if event.get("event_type") != "process":
        return None
    proc = _section(event)
    h = proc.get("hash_sha256")
    if not h or h in known_hashes:
        return None
    name = proc.get("name") or "unknown"
    return {
        "rule_id": "first-seen-binary",
        "rule_name": "First-seen binary executed",
        "severity": "LOW",
        "confidence": 40,
        "title": f"First-seen binary: {name}",
        "description": f"Device {event.get('device_id')} executed {name} whose hash has not been seen "
                       f"in this tenant before. Usually benign (updates, new installs) — review if unexpected.",
        "fingerprint": _fingerprint("first-seen-binary", event.get("device_id", ""), h),
        "evidence": {"name": name, "exe": proc.get("exe"), "hash_sha256": h,
                     "cmdline": (proc.get("cmdline") or [])[:10]},
    }


_RULES = (
    _rule_suspicious_cmdline,
    _rule_persistence_change,
    _rule_rare_outbound_port,
)


def match_rules(event: dict, known_hashes: set[str] | None = None) -> list[dict]:
    """Run all rules against one event dict. Returns findings (possibly empty)."""
    findings = []
    for rule in _RULES:
        hit = rule(event)
        if hit:
            findings.append(hit)
    if known_hashes is not None:
        hit = _rule_first_seen_binary(event, known_hashes)
        if hit:
            findings.append(hit)
    return findings
