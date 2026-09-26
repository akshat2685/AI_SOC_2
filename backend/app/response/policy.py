"""Autonomous response policy: alert -> device command, or alert -> approval.

SAFETY RULES (the whole point of this file — read before changing thresholds):

1. SCOPE: commands target ONLY the device that raised the alert
   (alert.device_id). The policy never addresses any other device, and the
   sensor only ever executes commands fetched for its own device_id.

2. EXACT PARAMS: every command param is an exact value lifted from the
   alert's evidence — a concrete pid, a literal process name, a literal IP,
   a literal registry path. Never a pattern, never a wildcard, never a
   substring. The sensor enforces the same rule client-side and refuses
   anything that looks like a pattern.

3. ALLOWLIST: only kill_process | block_ip | quarantine_file |
   remove_persistence exist. Unknown actions are refused by the backend
   (never created) and by the sensor (never executed).

4. DESTRUCTIVE GATE: quarantine_file and remove_persistence destroy data or
   system state, so they ALWAYS go through human approval — UNLESS the
   alert is severity CRITICAL *and* confidence >= 95. No rule currently
   emits CRITICAL, so today these are approval-only in practice.

5. AUTO GATE (no human in the loop): ALL of these must hold —
     - alert.severity in (HIGH, CRITICAL)
     - alert.confidence >= 80
     - alert detector is rules-based (evidence.detector startswith "rules-");
       ML-anomaly findings never auto-act, they go to approval.
   Anything else (MEDIUM severity, low confidence, ml-only detector,
   destructive action under the gate) creates an ApprovalRequest in the
   existing SOAR approval queue instead of a command.

6. LOW SEVERITY NEVER ACTS: severity LOW (or missing) produces nothing —
   no command, no approval, just a log line.

7. DEDUP: an identical pending/delivered command for the same device is
   never duplicated — repeated alerts don't stack 50 kill orders.

8. NEVER RAISE: every path is wrapped; a policy failure logs and returns,
   it never breaks ingest or detection.
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Alert,
    ApprovalRequest,
    ApprovalStatusEnum,
    Playbook,
    PlaybookExecution,
)
from app.response.models import (
    COMMAND_ACTIONS,
    DESTRUCTIVE_ACTIONS,
    DeviceCommand,
)

logger = logging.getLogger(__name__)

# --- thresholds (change here, documented above) ---
AUTO_SEVERITIES = ("HIGH", "CRITICAL")
AUTO_MIN_CONFIDENCE = 80
DESTRUCTIVE_MIN_CONFIDENCE = 95  # + severity must be CRITICAL

SYSTEM_PLAYBOOK_NAME = "Autonomous response"


def _detector(alert: Alert) -> str:
    ev = alert.evidence or {}
    return str(ev.get("detector") or "")


def _propose_actions(alert: Alert) -> list[dict]:
    """Build candidate actions from the alert's evidence. Exact values only."""
    ev = alert.evidence or {}
    rule_id = alert.rule_id or ""
    actions: list[dict] = []

    if rule_id == "suspicious-cmdline":
        proc = ev.get("process") or {}
        pid = proc.get("pid")
        name = proc.get("name")
        # pid is the most precise handle; the exact name rides along so the
        # sensor can verify the pid still belongs to the same process
        # (pids get recycled — never kill on a stale pid alone).
        params: dict = {}
        if isinstance(pid, int) and pid > 0:
            params["pid"] = pid
        if isinstance(name, str) and name and name != "unknown process":
            params["name"] = name
        if params:
            actions.append({"action": "kill_process", "params": params})

    elif rule_id == "rare-outbound-port":
        ip = str(ev.get("dst_ip") or "")
        try:
            if ip and ipaddress.ip_address(ip).is_global:
                actions.append({"action": "block_ip", "params": {"ip": ip}})
        except ValueError:
            pass

    elif rule_id == "persistence-change":
        path = str(ev.get("path") or "")
        if path:
            actions.append({"action": "remove_persistence", "params": {"path": path}})

    # Belt-and-braces: drop anything outside the allowlist, even though the
    # branches above only ever produce allowlisted actions.
    return [a for a in actions if a["action"] in COMMAND_ACTIONS]


async def _command_exists(db: AsyncSession, tenant_id: int, device_id: str,
                          action: str, params: dict) -> bool:
    stmt = select(DeviceCommand).where(
        DeviceCommand.tenant_id == tenant_id,
        DeviceCommand.device_id == device_id,
        DeviceCommand.action == action,
        DeviceCommand.status.in_(("pending", "delivered")),
    )
    for cmd in (await db.execute(stmt)).scalars().all():
        if (cmd.params or {}) == params:
            return True
    return False


async def _get_system_playbook(db: AsyncSession, tenant_id: int) -> Playbook:
    stmt = select(Playbook).where(
        Playbook.tenant_id == tenant_id, Playbook.name == SYSTEM_PLAYBOOK_NAME
    )
    pb = (await db.execute(stmt)).scalars().first()
    if pb:
        return pb
    pb = Playbook(
        tenant_id=tenant_id,
        name=SYSTEM_PLAYBOOK_NAME,
        description=(
            "System playbook backing autonomous response proposals. "
            "Executions carry the proposed device command in context_data; "
            "approving the request authorizes execution."
        ),
        definition={"kind": "system", "source": "response/policy.py"},
        is_active=True,
    )
    db.add(pb)
    await db.flush()
    return pb


async def _request_approval(db: AsyncSession, alert: Alert, actions: list[dict],
                            reason: str) -> dict:
    """Route proposed actions through the existing SOAR approval queue."""
    pb = await _get_system_playbook(db, alert.tenant_id)
    execution = PlaybookExecution(
        tenant_id=alert.tenant_id,
        playbook_id=pb.id,
        context_data={
            "kind": "autonomous-response-proposal",
            "alert_id": alert.id,
            "device_id": alert.device_id,
            "rule_id": alert.rule_id,
            "severity": alert.severity,
            "confidence": alert.confidence,
            "detector": _detector(alert),
            "proposed_actions": actions,
            "reason": reason,
        },
    )
    db.add(execution)
    await db.flush()
    ar = ApprovalRequest(
        tenant_id=alert.tenant_id,
        execution_id=execution.id,
        status=ApprovalStatusEnum.PENDING,
    )
    db.add(ar)
    await db.flush()
    logger.info(
        "response_approval_requested",
        alert_id=alert.id,
        device_id=alert.device_id,
        reason=reason,
        actions=[a["action"] for a in actions],
    )
    return {"outcome": "approval_requested", "approval_id": ar.id,
            "actions": [a["action"] for a in actions], "reason": reason}


async def evaluate_response_policy(db: AsyncSession, alert: Alert) -> dict:
    """Decide the response for one freshly-written alert.

    Returns a small dict describing what happened. Never raises.
    The caller must flush (so alert.id exists) before calling; this function
    only adds rows — the caller's commit persists them.
    """
    try:
        return await _evaluate(db, alert)
    except Exception as exc:  # safety rule 8
        logger.exception("response_policy_failed", alert_id=getattr(alert, "id", None),
                         error=str(exc))
        return {"outcome": "error", "reason": str(exc)}


async def _evaluate(db: AsyncSession, alert: Alert) -> dict:
    severity = (alert.severity or "").upper()
    confidence = alert.confidence or 0
    detector = _detector(alert)
    device_id = alert.device_id

    if not device_id:
        logger.info("response_skipped_no_device", alert_id=alert.id)
        return {"outcome": "skipped", "reason": "alert has no device_id"}

    # Safety rule 6: LOW (or missing) severity never acts.
    if severity not in ("MEDIUM", "HIGH", "CRITICAL"):
        logger.info("response_skipped_low_severity", alert_id=alert.id, severity=severity)
        return {"outcome": "none", "reason": f"severity {severity or 'unknown'} never acts"}

    actions = _propose_actions(alert)
    if not actions:
        logger.info("response_no_actions", alert_id=alert.id, rule_id=alert.rule_id)
        return {"outcome": "none", "reason": "no actionable evidence"}

    is_rules = detector.startswith("rules-")
    auto_eligible = (
        severity in AUTO_SEVERITIES
        and confidence >= AUTO_MIN_CONFIDENCE
        and is_rules
    )

    if not auto_eligible:
        reason = (
            f"auto gate not met (severity={severity}, confidence={confidence}, "
            f"detector={detector or 'unknown'})"
        )
        return await _request_approval(db, alert, actions, reason)

    # Auto path — but destructive actions still need the strict gate.
    auto_actions: list[dict] = []
    for a in actions:
        if a["action"] in DESTRUCTIVE_ACTIONS and not (
            severity == "CRITICAL" and confidence >= DESTRUCTIVE_MIN_CONFIDENCE
        ):
            return await _request_approval(
                db, alert, actions,
                f"destructive action '{a['action']}' requires approval "
                f"(needs CRITICAL + confidence >= {DESTRUCTIVE_MIN_CONFIDENCE})",
            )
        auto_actions.append(a)

    created: list[int] = []
    for a in auto_actions:
        if await _command_exists(db, alert.tenant_id, device_id, a["action"], a["params"]):
            logger.info("response_command_deduped", alert_id=alert.id,
                        device_id=device_id, action=a["action"])
            continue
        cmd = DeviceCommand(
            tenant_id=alert.tenant_id,
            device_id=device_id,
            action=a["action"],
            params=a["params"],
            status="pending",
        )
        db.add(cmd)
        await db.flush()
        created.append(cmd.id)
        logger.info(
            "response_command_created",
            command_id=cmd.id,
            alert_id=alert.id,
            device_id=device_id,
            action=a["action"],
            params=a["params"],
        )
    return {"outcome": "auto_commands", "command_ids": created,
            "actions": [a["action"] for a in auto_actions]}
