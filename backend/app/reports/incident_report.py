"""Incident report builder — markdown assembled purely from DB rows.

Every section derives from stored rows (incidents, alerts, endpoint_agents,
approvals). Nothing is inferred beyond simple counts and direct field
reads; empty sections say so explicitly. No LLM, no invented content.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.detection.rules import _is_public_ip
from app.domain.models import (
    Alert,
    ApprovalRequest,
    EndpointAgent,
    Incident,
    PlaybookExecution,
    Tenant,
)

REPORT_VERSION = "incident-report-v1"
_MAX_IOCS = 50  # cap per indicator list

# ---------------------------------------------------------------------------
# MITRE ATT&CK mapping.
#
# Built from the rule definitions in app/detection/rules.py. The "matched"
# strings below are copied verbatim from _SUSPICIOUS_CMDLINE descriptions, so
# per-alert refinement is a direct lookup, not a guess. Rules with no
# technique attribution are marked "unmapped" — never invented.
# ---------------------------------------------------------------------------

# (matched description substring, technique_id, tactic, technique name)
_CMDLINE_TECHNIQUES: list[tuple[str, str, str, str]] = [
    ("PowerShell with encoded command or hidden window",
     "T1059.001", "Execution", "Command and Scripting Interpreter: PowerShell"),
    ("Mimikatz credential dumper",
     "T1003.001", "Credential Access", "OS Credential Dumping: LSASS Memory"),
    ("PsExec remote execution tool",
     "T1021.002", "Lateral Movement", "Remote Services: SMB/Windows Admin Shares"),
    ("WMIC remote process creation",
     "T1047", "Execution", "Windows Management Instrumentation"),
    ("Volume shadow copy deletion (ransomware behavior)",
     "T1490", "Impact", "Inhibit System Recovery"),
    ("Boot recovery disabled",
     "T1490", "Impact", "Inhibit System Recovery"),
    ("NTDS database access attempt",
     "T1003.003", "Credential Access", "OS Credential Dumping: NTDS"),
    ("Registry hive exfiltration (SAM/SYSTEM/SECURITY)",
     "T1003.002", "Credential Access", "OS Credential Dumping: Security Account Manager"),
    ("CertUtil used to decode a payload (living-off-the-land)",
     "T1105", "Command and Control", "Ingress Tool Transfer"),
    ("BITSAdmin used for download (living-off-the-land)",
     "T1105", "Command and Control", "Ingress Tool Transfer"),
    ("Rundll32 executing DLL export by ordinal",
     "T1218.011", "Defense Evasion", "System Binary Proxy Execution: Rundll32"),
    ("Mshta fetching remote payload",
     "T1218.005", "Defense Evasion", "System Binary Proxy Execution: Mshta"),
    ("Script host with remote VBS",
     "T1059.005", "Execution", "Command and Scripting Interpreter: Visual Basic"),
    ("Local user account creation via net.exe",
     "T1136", "Persistence", "Create Account: Local Account"),
    ("LSASS memory dumping tooling",
     "T1003.001", "Credential Access", "OS Credential Dumping: LSASS Memory"),
]

# rule_id -> (technique_id, tactic, technique name, mapping note)
RULE_MITRE: dict[str, tuple[str | None, str | None, str | None, str]] = {
    "suspicious-cmdline": (
        "T1059*", "Execution*", "Command and Scripting Interpreter*",
        "refined per alert from the matched pattern (see table); "
        "default T1059 when the matched pattern is unavailable",
    ),
    "persistence-change": (
        "T1547.001", "Persistence",
        "Boot or Logon Autostart Execution: Registry Run Keys / Startup Folder",
        "Run-key autorun persistence",
    ),
    "rare-outbound-port": (
        "T1571", "Command and Control", "Non-Standard Port",
        "outbound to a public IP on an uncommon port",
    ),
    "brute-force-auth": (
        "T1110", "Credential Access", "Brute Force",
        "many failed authentication attempts in a short window",
    ),
    "known-c2-connection": (
        "T1071", "Command and Control", "Application Layer Protocol",
        "connection to infrastructure present in the threat-intel feed",
    ),
    "known-malicious-connection": (
        None, None, None,
        "unmapped — destination is known-malicious per the intel feed but not "
        "specifically classified as C2; no technique attribution claimed",
    ),
    "first-seen-binary": (
        None, None, None,
        "unmapped — behavioral observation (new binary executed), "
        "no technique attribution",
    ),
    "ml-anomaly": (
        None, None, None,
        "unmapped — behavioral anomaly detector, not a signature; "
        "no technique attribution",
    ),
}

# Plain-language one-liners per rule for the "What happened" section.
_RULE_SUMMARIES: dict[str, str] = {
    "suspicious-cmdline": "suspicious command line(s) executed",
    "persistence-change": "autorun persistence change(s) (Run-key value created/modified)",
    "rare-outbound-port": "outbound connection(s) to public IPs on uncommon ports",
    "brute-force-auth": "brute-force authentication attempt(s)",
    "known-c2-connection": "connection(s) to known malicious infrastructure (threat intel)",
    "known-malicious-connection": "connection(s) to known-malicious infrastructure (threat intel, not C2-classified)",
    "first-seen-binary": "first-seen binar(ies) executed",
    "ml-anomaly": "hour(s) of behavior flagged anomalous by the ML model",
}

_DOMAIN_RE = re.compile(r"https?://([A-Za-z0-9.\-]+)", re.IGNORECASE)


def _esc(cell: Any) -> str:
    """Escape a value for use inside a markdown table cell."""
    return str(cell if cell is not None else "").replace("|", "\\|").replace("\n", " ")


def _fmt_ts(ts: datetime | None) -> str:
    if not ts:
        return "unknown"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def map_alert_to_technique(alert: Alert) -> tuple[str | None, str | None, str | None]:
    """Return (technique_id, tactic, technique_name) for an alert.

    suspicious-cmdline alerts are refined via the stored "matched"
    description; anything without a defensible mapping returns Nones
    (rendered as "unmapped").
    """
    rule_id = (alert.rule_id or "").strip()
    if rule_id == "suspicious-cmdline":
        matched = str(((alert.evidence or {}).get("matched")) or "")
        for desc, tid, tactic, name in _CMDLINE_TECHNIQUES:
            if desc in matched:
                return tid, tactic, name
        return "T1059", "Execution", "Command and Scripting Interpreter"
    entry = RULE_MITRE.get(rule_id)
    if entry:
        return entry[0], entry[1], entry[2]
    return None, None, None


def _detector_label(alert: Alert) -> str:
    ev = alert.evidence or {}
    det = ev.get("detector") or "unknown"
    mv = ev.get("model_version")
    return f"{det} (model {mv})" if mv else str(det)


async def build_incident_report(db: AsyncSession, incident_id: int) -> str:
    """Build a markdown incident report for one incident. Pure DB reads."""
    incident = (await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )).scalars().first()
    if not incident:
        raise ValueError(f"incident {incident_id} not found")

    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == incident.tenant_id)
    )).scalars().first()

    alerts = (await db.execute(
        select(Alert)
        .where(Alert.incident_id == incident_id, Alert.tenant_id == incident.tenant_id)
        .order_by(Alert.timestamp.asc())
    )).scalars().all()

    device_ids = sorted({a.device_id for a in alerts if a.device_id})
    hostnames: dict[str, str] = {}
    if device_ids:
        rows = (await db.execute(
            select(EndpointAgent.device_id, EndpointAgent.hostname).where(
                EndpointAgent.tenant_id == incident.tenant_id,
                EndpointAgent.device_id.in_(device_ids),
            )
        )).all()
        hostnames = {d: h for d, h in rows}

    lines: list[str] = []
    add = lines.append

    # ---- header -----------------------------------------------------------
    sev = incident.severity.value if incident.severity else "UNKNOWN"
    stat = incident.status.value if incident.status else "UNKNOWN"
    add(f"# Incident report: #{incident.id} — {_esc(incident.title)}")
    add("")
    add(f"- **Incident ID:** {incident.id}")
    add(f"- **Title:** {_esc(incident.title)}")
    add(f"- **Severity:** {sev}")
    add(f"- **Status:** {stat}")
    add(f"- **Verdict:** {_esc(incident.verdict or 'UNKNOWN')}")
    add(f"- **Opened:** {_fmt_ts(incident.created_at)}")
    if stat in ("RESOLVED", "CLOSED"):
        add(f"- **Closed:** {_fmt_ts(incident.updated_at)} "
            f"(last update time — no dedicated closed timestamp is stored)")
    else:
        add("- **Closed:** still open")
    add(f"- **Tenant:** {_esc(tenant.name) if tenant else incident.tenant_id} "
        f"(id {incident.tenant_id})")
    if device_ids:
        dev_str = ", ".join(
            f"{d}" + (f" ({hostnames[d]})" if hostnames.get(d) else "")
            for d in device_ids
        )
        add(f"- **Affected device(s):** {_esc(dev_str)}")
    else:
        add("- **Affected device(s):** none recorded on linked alerts")
    add(f"- **Linked alerts:** {len(alerts)}")
    add("")

    # ---- what happened ----------------------------------------------------
    add("## What happened")
    add("")
    if not alerts:
        add("No alerts are linked to this incident, so there is no observed "
            "activity to summarize.")
    else:
        rule_counts = Counter((a.rule_id or "unknown").strip() or "unknown" for a in alerts)
        sev_counts = Counter((a.severity or "UNKNOWN").upper() for a in alerts)
        detectors = sorted({_detector_label(a) for a in alerts})
        parts = []
        for rid, n in rule_counts.most_common():
            label = _RULE_SUMMARIES.get(rid, f"{rid} alert(s)")
            parts.append(f"{n} {label}")
        add(f"This incident groups **{len(alerts)} alert(s)**: " + "; ".join(parts) + ".")
        add("")
        add("Severity mix: " + ", ".join(
            f"{c} {s}" for s, c in sorted(sev_counts.items())) + ".")
        add("")
        add("Scored by: " + ", ".join(f"`{_esc(d)}`" for d in detectors) + ".")
        # per-rule detail with matched patterns (cmdline only, from evidence)
        matched = sorted({
            str((a.evidence or {}).get("matched"))
            for a in alerts
            if a.rule_id == "suspicious-cmdline" and (a.evidence or {}).get("matched")
        })
        if matched:
            add("")
            add("Observed malicious-pattern matches: " +
                "; ".join(f"`{_esc(m)}`" for m in matched) + ".")
    add("")

    # ---- MITRE mapping ----------------------------------------------------
    add("## MITRE ATT&CK mapping")
    add("")
    add("| Rule | Technique | Tactic | Technique name |")
    add("|---|---|---|---|")
    seen_rules = sorted({(a.rule_id or "unknown").strip() or "unknown" for a in alerts})
    if not seen_rules:
        add("| _none_ | — | — | no alerts, no mapping |")
    else:
        for rid in seen_rules:
            if rid == "suspicious-cmdline":
                # one row per distinct refined technique observed
                refinements: dict[tuple, int] = Counter()
                for a in alerts:
                    if (a.rule_id or "").strip() == "suspicious-cmdline":
                        refinements[map_alert_to_technique(a)] += 1
                for (tid, tactic, name), n in sorted(refinements.items()):
                    add(f"| {_esc(rid)} (x{n}) | {_esc(tid)} | {_esc(tactic)} | {_esc(name)} |")
            else:
                entry = RULE_MITRE.get(rid)
                if entry and entry[0]:
                    add(f"| {_esc(rid)} | {_esc(entry[0])} | {_esc(entry[1])} | {_esc(entry[2])} |")
                else:
                    note = entry[3] if entry else "unmapped — no technique attribution"
                    add(f"| {_esc(rid)} | unmapped | — | {_esc(note)} |")
    add("")
    add("_Mappings come from the rule definitions in `app/detection/rules.py`; "
        "rules with no defensible technique attribution are marked unmapped._")
    add("")

    # ---- timeline ---------------------------------------------------------
    add("## Timeline")
    add("")
    if not alerts:
        add("No alerts linked — timeline is empty.")
    else:
        add("| Time (UTC) | Alert | Severity | Confidence | Detector |")
        add("|---|---|---|---|---|")
        for a in alerts:
            add(f"| {_fmt_ts(a.timestamp)} | {_esc(a.rule_name or a.rule_id or a.id)} "
                f"| {_esc((a.severity or 'UNKNOWN').upper())} "
                f"| {a.confidence if a.confidence is not None else 'n/a'} "
                f"| {_esc(_detector_label(a))} |")
    add("")

    # ---- indicators -------------------------------------------------------
    add("## Indicators")
    add("")
    ips: set[str] = set()
    domains: set[str] = set()
    ports: set[str] = set()
    procs: set[str] = set()
    paths: set[str] = set()
    for a in alerts:
        ev = a.evidence or {}
        dip = str(ev.get("dst_ip") or "")
        if dip and _is_public_ip(dip) is True:
            ips.add(dip)
        port = ev.get("dst_port")
        if port:
            ports.add(str(port))
        for key in ("process_name",):
            if ev.get(key):
                procs.add(str(ev[key]))
        proc = ev.get("process") or {}
        if isinstance(proc, dict):
            if proc.get("name"):
                procs.add(str(proc["name"]))
            if proc.get("exe"):
                paths.add(str(proc["exe"]))
        if ev.get("name") and a.rule_id == "first-seen-binary":
            procs.add(str(ev["name"]))
        if ev.get("path"):
            paths.add(str(ev["path"]))
        for blob in (str(ev.get("cmdline") or ""), str(a.description or "")):
            for m in _DOMAIN_RE.findall(blob):
                if "." in m:
                    domains.add(m.lower())

    def _ioc_block(title: str, values: set[str]) -> None:
        vals = sorted(values)[:_MAX_IOCS]
        add(f"**{title}** ({len(values)} unique"
            + (f", showing first {_MAX_IOCS}" if len(values) > _MAX_IOCS else "") + "):")
        if vals:
            add("")
            for v in vals:
                add(f"- `{_esc(v)}`")
        else:
            add(" none observed.")
        add("")

    if not alerts:
        add("No alerts linked — no indicators extracted.")
        add("")
    else:
        _ioc_block("External IPs", ips)
        _ioc_block("Domains", domains)
        _ioc_block("Ports", ports)
        _ioc_block("Process names", procs)
        _ioc_block("File paths", paths)

    # ---- response actions --------------------------------------------------
    add("## Response actions")
    add("")
    commands = await _device_commands_for_incident(db, incident)
    if commands is None:
        add("The device command channel is not yet deployed in this build — "
            "no response actions have been issued from the SOC for this incident.")
    elif not commands:
        add("No device commands have been issued for this incident.")
    else:
        add("| Action | Target | Status | Result |")
        add("|---|---|---|---|")
        for c in commands:
            add(f"| {_esc(c['action'])} | {_esc(c['target'])} | "
                f"{_esc(c['status'])} | {_esc(c['result'])} |")
    add("")
    approvals = await _approvals_for_incident(db, incident)
    if not approvals:
        add("Approval requests: none linked to this incident.")
    else:
        add("Approval requests linked to this incident:")
        add("")
        for ap in approvals:
            add(f"- Request #{ap['id']}: **{ap['status']}** "
                f"(playbook execution #{ap['execution_id']}, "
                f"requested {_fmt_ts(ap['created_at'])})")
    add("")

    # ---- remediation status ------------------------------------------------
    add("## Remediation status")
    add("")
    if commands is None or not commands:
        add("No remediation actions have been recorded for this incident — "
            "containment status is **unknown**.")
    else:
        done = [c for c in commands
                if str(c["status"]).lower() in ("success", "succeeded", "completed", "delivered", "done")]
        pending = [c for c in commands if c not in done]
        add(f"- **Contained/resolved actions:** {len(done)} of {len(commands)}")
        add(f"- **Pending/failed actions:** {len(pending)} of {len(commands)}")
        if pending:
            add("- Pending: " + "; ".join(
                f"`{_esc(c['action'])}` on {_esc(c['target'])} ({_esc(c['status'])})"
                for c in pending))
        if not pending and done:
            add("- All recorded response actions completed — incident is contained "
                "as far as the SOC's own actions show.")
    add("")

    # ---- analyst notes ------------------------------------------------------
    add("## Analyst notes")
    add("")
    if incident.analyst_notes and incident.analyst_notes.strip():
        add(incident.analyst_notes.strip())
    else:
        add("No analyst notes recorded.")
    add("")

    # ---- footer --------------------------------------------------------------
    add("---")
    add(f"_Report generated {_fmt_ts(datetime.now(timezone.utc))} by {REPORT_VERSION}. ")
    detectors_used = sorted({_detector_label(a) for a in alerts}) or ["none — no alerts"]
    add(f"Detectors that scored this incident: {', '.join(f'`{_esc(d)}`' for d in detectors_used)}. ")
    ml_versions = sorted({str((a.evidence or {}).get("model_version"))
                          for a in alerts if (a.evidence or {}).get("model_version")})
    if ml_versions:
        add(f"ML model version(s): {', '.join(ml_versions)}. ")
    trained = sorted({str((a.evidence or {}).get("model_trained_on"))
                      for a in alerts if (a.evidence or {}).get("model_trained_on")})
    if trained:
        add(f"Model training provenance: {', '.join(f'`{_esc(t)}`' for t in trained)}. ")
    add("Every section above derives from stored database rows; empty sections "
        "say so explicitly — nothing was inferred or invented._")

    return "\n".join(lines) + "\n"


async def _device_commands_for_incident(
    db: AsyncSession, incident: Incident
) -> list[dict] | None:
    """Return device commands for the incident, or None if the channel
    isn't deployed yet (model/table built in a parallel track)."""
    try:
        from app.domain.models import DeviceCommand  # type: ignore
    except ImportError:
        return None
    # The parallel track owns this schema; read it defensively.
    cols = {c.name for c in DeviceCommand.__table__.columns}
    if "incident_id" not in cols:
        return []
    stmt = select(DeviceCommand).where(
        DeviceCommand.__table__.c.incident_id == incident.id
    )
    try:
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:
        return []
    out = []
    for r in rows:
        def _get(*names: str, default: str = "") -> str:
            for n in names:
                if hasattr(r, n) and getattr(r, n) is not None:
                    return str(getattr(r, n))
            return default
        out.append({
            "action": _get("action", "command", "command_type", default="unknown"),
            "target": _get("device_id", "target", "hostname", default="unknown"),
            "status": _get("status", "state", default="unknown"),
            "result": _get("result", "output", "detail", default=""),
        })
    return out


async def _approvals_for_incident(db: AsyncSession, incident: Incident) -> list[dict]:
    """Approval requests whose playbook execution context references this
    incident. Approvals are playbook-linked (no incident FK), so the link
    is derived from execution context_data — never assumed."""
    out: list[dict] = []
    try:
        execs = (await db.execute(
            select(PlaybookExecution).where(PlaybookExecution.tenant_id == incident.tenant_id)
            .order_by(PlaybookExecution.id.desc()).limit(200)
        )).scalars().all()
    except Exception:
        return out
    needle = str(incident.id)
    linked_exec_ids = {
        e.id for e in execs
        if needle in str(e.context_data or "")
    }
    if not linked_exec_ids:
        return out
    try:
        reqs = (await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.tenant_id == incident.tenant_id,
                ApprovalRequest.execution_id.in_(linked_exec_ids),
            )
        )).scalars().all()
    except Exception:
        return out
    for r in reqs:
        out.append({
            "id": r.id,
            "execution_id": r.execution_id,
            "status": r.status.value if r.status else "UNKNOWN",
            "created_at": r.created_at,
        })
    return out
