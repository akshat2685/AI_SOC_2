import structlog
import httpx
import ipaddress
from collections import defaultdict, deque
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.infrastructure.database import get_db
from app.core.config import settings
from app.core.auth import current_tenant_id
from app.api.deps import require_roles_dual
from app.domain.models import (
    Asset, Alert, Incident, AuditEvent, ApprovalRequest, PlaybookExecution,
    Playbook, RoleEnum, ApprovalStatusEnum, StatusEnum, SeverityEnum,
    CriticalityEnum,
)

router = APIRouter()
logger = structlog.get_logger(__name__)

# Reads: any authenticated role. Writes: analyst or admin.
READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]
ADMIN_ROLES = [RoleEnum.TENANT_ADMIN]

# ---------------------------------------------------------------------------
# Dashboard & Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    try:
        inc_count = (await db.execute(select(func.count(Incident.id)))).scalar() or 0
        alert_count = (await db.execute(select(func.count(Alert.id)))).scalar() or 0
    except Exception:
        inc_count = 0
        alert_count = 0
    return {
        "active_incidents": inc_count,
        "open_alerts": alert_count,
        "threats_blocked": 0,
        "system_health": "healthy",
    }

async def _gemini_generate(prompt_text: str, system_text: str) -> str:
    """Call Gemini generateContent and return the text answer.

    Raises HTTPException 503 when GEMINI_API_KEY is unset, 502 on provider
    failure. Shared by /chat and /copilot/chat.
    """
    api_key = settings.GEMINI_API_KEY
    model = settings.GEMINI_MODEL or "gemini-3.5-flash"
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI Copilot is not configured: set GEMINI_API_KEY in the backend environment and redeploy.",
        )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                json={
                    "system_instruction": {"parts": [{"text": system_text}]},
                    "contents": [{"parts": [{"text": prompt_text}]}],
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
                },
            )
    except httpx.HTTPError as e:
        logger.error("gemini_upstream_unreachable", error=str(e))
        raise HTTPException(status_code=502, detail="AI provider unreachable; try again shortly.")

    if resp.status_code == 404:
        raise HTTPException(
            status_code=502,
            detail=f"Model '{model}' is not available for this API key; set GEMINI_MODEL to a supported model.",
        )
    if resp.status_code != 200:
        logger.error("gemini_provider_error", status=resp.status_code, body=resp.text[:500])
        raise HTTPException(status_code=502, detail="AI provider returned an error; try again shortly.")

    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="AI provider returned an unreadable response.")


@router.post("/chat")
async def chat(
    data: dict,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    """SOC Copilot chat backed by Gemini. Requires GEMINI_API_KEY on the backend."""
    query = str(data.get("query") or data.get("message") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Provide 'query' in the request body.")

    model = settings.GEMINI_MODEL or "gemini-3.5-flash"

    # Optional alert context for grounded answers.
    context_block = ""
    alert_id = data.get("alert_id")
    if alert_id is not None:
        try:
            tenant_id = current_tenant_id.get() or 1
            result = await db.execute(
                select(Alert).where(Alert.id == int(alert_id), Alert.tenant_id == tenant_id)
            )
            alert = result.scalars().first()
            if alert:
                context_block = (
                    f"\n\nAlert context: rule='{alert.rule_name}', source='{alert.source}', "
                    f"description='{(alert.description or '')[:500]}'."
                )
        except (ValueError, TypeError):
            pass

    system = (
        "You are ShieldAI SOC Copilot, an assistant for security analysts. "
        "Answer concisely and practically, with concrete next steps. "
        "If asked about non-security topics, answer briefly and steer back to security operations."
    )
    text = await _gemini_generate(query + context_block, system)
    logger.info("chat_answered", model=model, query_len=len(query))
    return {"response": text, "model": model}


@router.post("/copilot/chat")
async def copilot_chat(
    data: dict,
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """SOC Copilot chat in the shape the frontend drawer calls.

    Request:  {conversation_id, question, history, context_drilldown}
    Response: {answer, citations, reasoning_steps, confidence_score}
    Requires GEMINI_API_KEY on the backend; honest 503 until it is set.
    """
    question = str(data.get("question") or data.get("query") or data.get("message") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Provide 'question' in the request body.")

    history = data.get("history")
    hist_block = ""
    if isinstance(history, list) and history:
        turns = []
        for m in history[-6:]:
            if isinstance(m, dict):
                turns.append(f"{m.get('role', 'user')}: {str(m.get('content', ''))[:400]}")
        if turns:
            hist_block = "\n\nConversation so far:\n" + "\n".join(turns)

    system = (
        "You are ShieldAI SOC Copilot, an assistant for security analysts. "
        "Answer concisely and practically, with concrete next steps. "
        "If asked about non-security topics, answer briefly and steer back to security operations."
    )
    answer = await _gemini_generate(question + hist_block, system)
    logger.info("copilot_chat_answered", query_len=len(question))
    return {
        "answer": answer,
        "citations": [],
        "reasoning_steps": [],
        "confidence_score": 0.9,
        "model": settings.GEMINI_MODEL or "gemini-3.5-flash",
    }

# ---------------------------------------------------------------------------
# MITRE ATT&CK (live dataset, bundled from MITRE CTI)
# ---------------------------------------------------------------------------

import json as _json
import os as _os

_ATTACK_PATH = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), "..", "..", "data", "attack_enterprise.json"))
_ATTACK = None


def _attack_data() -> dict:
    """Lazy-load the bundled ATT&CK Enterprise dataset (degrades to empty)."""
    global _ATTACK
    if _ATTACK is None:
        try:
            with open(_ATTACK_PATH) as f:
                _ATTACK = _json.load(f)
        except (OSError, ValueError):
            _ATTACK = {"techniques": [], "tactics": [], "mitigations": [],
                       "technique_mitigations": {}, "retrieved_at": None,
                       "source": "mitre-cti"}
    return _ATTACK


# Keyword -> technique mappings for alert rule names (kept from the curated build).
RULE_MAPPINGS = [
    {"rule_pattern": "powershell", "technique_id": "T1059.001"},
    {"rule_pattern": "brute force", "technique_id": "T1110.001"},
    {"rule_pattern": "failed login", "technique_id": "T1110"},
    {"rule_pattern": "ransomware", "technique_id": "T1486"},
    {"rule_pattern": "shadow copy", "technique_id": "T1490"},
    {"rule_pattern": "mimikatz", "technique_id": "T1003.001"},
    {"rule_pattern": "lsass", "technique_id": "T1003.001"},
    {"rule_pattern": "lateral movement", "technique_id": "T1021"},
    {"rule_pattern": "ssh", "technique_id": "T1021.004"},
    {"rule_pattern": "rdp", "technique_id": "T1021"},
    {"rule_pattern": "c2", "technique_id": "T1071"},
    {"rule_pattern": "command and control", "technique_id": "T1071"},
    {"rule_pattern": "exfiltration", "technique_id": "T1041"},
    {"rule_pattern": "dns tunneling", "technique_id": "T1048"},
    {"rule_pattern": "phishing", "technique_id": "T1566"},
    {"rule_pattern": "port scan", "technique_id": "T1595"},
    {"rule_pattern": "process injection", "technique_id": "T1055"},
    {"rule_pattern": "credential dumping", "technique_id": "T1003"},
]


def _technique_summary(t: dict) -> dict:
    tactics = t.get("tactics") or []
    return {"id": t["id"], "name": t["name"],
            "tactic": tactics[0] if tactics else "",
            "description": t.get("description", "")}


@router.get("/mitre/mappings")
async def get_mitre_mappings(
    limit: int = Query(100, ge=1, le=697, description="Page size (use with offset)"),
    offset: int = Query(0, ge=0, description="Skip first N techniques"),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Full MITRE ATT&CK Enterprise dataset + rule-pattern mappings.

    Techniques come from the bundled live pull of MITRE CTI
    (backend/app/data/attack_enterprise.json), not a hand-curated subset.
    Paginated: the full 697-technique payload is ~480KB, which is flaky
    over HTTP/1.1 through the CDN — page it instead of fetching all at once.
    """
    data = _attack_data()
    techniques = [_technique_summary(t) for t in data["techniques"]]
    total = len(techniques)
    page = techniques[offset:offset + limit]
    return {
        "techniques": page,
        "rule_mappings": RULE_MAPPINGS,
        "count": len(page),
        "total": total,
        "limit": limit,
        "offset": offset,
        "source": data.get("source", "mitre-cti"),
        "retrieved_at": data.get("retrieved_at"),
        "note": ("Full MITRE ATT&CK Enterprise dataset (techniques incl. "
                 "sub-techniques). Re-run the ATT&CK pipeline to refresh."),
    }


@router.get("/mitre/techniques")
async def search_techniques(
    q: str = Query("", description="Substring over id, name, description"),
    tactic: str = Query("", description="Tactic name filter"),
    platform: str = Query("", description="Platform filter, e.g. Windows"),
    limit: int = Query(50, ge=1, le=200),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Search the bundled ATT&CK Enterprise techniques."""
    data = _attack_data()
    ql, tl, pl = q.lower(), tactic.lower(), platform.lower()
    out = []
    for t in data["techniques"]:
        if ql and ql not in f"{t['id']} {t['name']} {t.get('description', '')}".lower():
            continue
        if tl and not any(tl in x.lower() for x in (t.get("tactics") or [])):
            continue
        if pl and not any(pl in x.lower() for x in (t.get("platforms") or [])):
            continue
        out.append({**_technique_summary(t),
                    "tactics": t.get("tactics") or [],
                    "platforms": t.get("platforms") or []})
        if len(out) >= limit:
            break
    return {"techniques": out, "count": len(out), "total": len(data["techniques"])}


@router.get("/mitre/techniques/{technique_id}")
async def get_technique(
    technique_id: str,
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Technique detail with mapped mitigations."""
    data = _attack_data()
    tid = technique_id.upper()
    t = next((x for x in data["techniques"] if x["id"] == tid), None)
    if not t:
        raise HTTPException(status_code=404, detail=f"Technique '{technique_id}' not found.")
    mids = (data.get("technique_mitigations") or {}).get(tid, [])
    mit_by_id = {m["id"]: m for m in data.get("mitigations", [])}
    return {
        **_technique_summary(t),
        "tactics": t.get("tactics") or [],
        "platforms": t.get("platforms") or [],
        "data_sources": t.get("data_sources") or [],
        "mitigations": [mit_by_id[m] for m in mids if m in mit_by_id],
    }


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Tenant-scoped audit trail with on-read chain verification.

    RLS (tenant role) already scopes every row to the caller's tenant; the
    explicit tenant_id filter is defense in depth. The tamper-evident hash
    chain is re-verified over the returned page, anchored on the preceding
    row's hash (or genesis for the first page).
    """
    from app.application.audit_logger import verify_chain, _GENESIS

    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")

    rows = (
        await db.execute(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(desc(AuditEvent.id))
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()

    events = [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "user_id": r.user_id,
            "trace_id": r.trace_id,
            "action": r.action,
            "details": r.details,
            "integrity_hash": r.integrity_hash,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

    chain_valid, chain_error = True, None
    if rows:
        ascending = list(reversed(events))
        if skip == 0:
            anchor = None  # genesis
        else:
            anchor = (
                await db.execute(
                    select(AuditEvent.integrity_hash)
                    .where(AuditEvent.tenant_id == tenant_id, AuditEvent.id < rows[-1].id)
                    .order_by(desc(AuditEvent.id))
                    .limit(1)
                )
            ).scalar_one_or_none()
        if skip != 0 and anchor is None:
            chain_valid, chain_error = False, "missing chain anchor (possible row deletion)"
        else:
            valid, failed_id = verify_chain(ascending, anchor or _GENESIS)
            chain_valid = valid
            if not valid:
                chain_error = f"chain broken at event {failed_id} (possible tampering)"

    logger.info("audit_log_listed", count=len(events), tenant_id=tenant_id, chain_valid=chain_valid)
    return {
        "events": events,
        "chain_valid": chain_valid,
        "chain_error": chain_error,
        "signing": "hmac-sha256",
    }

# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@router.get("/approvals")
async def get_approvals(
    status_filter: str = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    """SOAR approval queue: pending human decisions on automated actions."""
    tenant_id = current_tenant_id.get() or 1
    stmt = (
        select(ApprovalRequest, PlaybookExecution, Playbook)
        .join(PlaybookExecution, ApprovalRequest.execution_id == PlaybookExecution.id)
        .join(Playbook, PlaybookExecution.playbook_id == Playbook.id)
        .where(ApprovalRequest.tenant_id == tenant_id)
        .order_by(desc(ApprovalRequest.created_at))
    )
    if status_filter:
        try:
            stmt = stmt.where(ApprovalRequest.status == ApprovalStatusEnum(status_filter.upper()))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status filter '{status_filter}'.")

    rows = (await db.execute(stmt)).all()
    queue = []
    for ar, ex, pb in rows:
        queue.append({
            "id": ar.id,
            "execution_id": ar.execution_id,
            "playbook_id": ex.playbook_id,
            "playbook_name": pb.name,
            "status": ar.status.value if ar.status else "UNKNOWN",
            "requester_id": ar.requester_id,
            "approver_id": ar.approver_id,
            "context": ex.context_data or {},
            "created_at": ar.created_at.isoformat() if ar.created_at else None,
        })
    logger.info("approvals_listed", tenant_id=tenant_id, count=len(queue))
    return {"approvals": queue, "count": len(queue)}


@router.post("/approvals/{approval_id}/approve")
async def approve_request(
    approval_id: int,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(ADMIN_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id, ApprovalRequest.tenant_id == tenant_id
        )
    )
    ar = result.scalars().first()
    if not ar:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if ar.status != ApprovalStatusEnum.PENDING:
        raise HTTPException(status_code=409, detail=f"Request already {ar.status.value}")
    ar.status = ApprovalStatusEnum.APPROVED
    # Approve -> execute bridge: an approved autonomous-response request turns
    # its proposed actions into DeviceCommands the sensor picks up (~30s poll).
    created_commands = 0
    try:
        from app.response.models import DeviceCommand as _DeviceCommand

        ex_result = await db.execute(
            select(PlaybookExecution).where(
                PlaybookExecution.id == ar.execution_id,
                PlaybookExecution.tenant_id == tenant_id,
            )
        )
        execution = ex_result.scalars().first()
        if execution:
            ctx = execution.context_data or {}
            for action in ctx.get("proposed_actions", []) or []:
                device_id = str(action.get("device_id") or "").strip()
                name = str(action.get("action") or "").strip()
                if not device_id or name not in (
                    "kill_process", "block_ip", "quarantine_file", "remove_persistence"
                ):
                    continue
                db.add(_DeviceCommand(
                    tenant_id=tenant_id,
                    device_id=device_id,
                    action=name,
                    params=action.get("params") or {},
                    status="pending",
                ))
                created_commands += 1
    except Exception:
        logger.error("approval_execute_bridge_failed", approval_id=approval_id, exc_info=True)
    await db.commit()
    logger.info("approval_approved", approval_id=approval_id, tenant_id=tenant_id,
                commands_created=created_commands)
    return {"status": "success", "id": ar.id, "new_status": "APPROVED",
            "commands_created": created_commands}


@router.post("/approvals/{approval_id}/reject")
async def reject_request(
    approval_id: int,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(ADMIN_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id, ApprovalRequest.tenant_id == tenant_id
        )
    )
    ar = result.scalars().first()
    if not ar:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if ar.status != ApprovalStatusEnum.PENDING:
        raise HTTPException(status_code=409, detail=f"Request already {ar.status.value}")
    ar.status = ApprovalStatusEnum.REJECTED
    await db.commit()
    logger.info("approval_rejected", approval_id=approval_id, tenant_id=tenant_id)
    return {"status": "success", "id": ar.id, "new_status": "REJECTED"}

# ---------------------------------------------------------------------------
# Payments (sandbox — no real charges, no card data stored)
# ---------------------------------------------------------------------------
# Billing is simulated in this MVP: there is no payment provider wired up,
# so every operation runs in sandbox mode. Card fields sent by the client
# are accepted and immediately discarded — never logged, never persisted.

SANDBOX_PLANS = {
    "free": {"price": 0, "limits": "Community: 100 alerts/day"},
    "pro": {"price": 999, "currency": "INR", "limits": "Unlimited alerts, SOAR playbooks, API keys"},
    "enterprise": {"price": 4999, "currency": "INR", "limits": "Everything in Pro + SSO, audit exports, SLA"},
}


@router.get("/payments/status")
async def get_payment_status(
    username: str = Query(None),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    logger.info("payment_status_checked", username=username)
    return {
        "mode": "sandbox",
        "plan": "free",
        "status": "active",
        "username": username,
        "available_plans": SANDBOX_PLANS,
        "message": "Sandbox billing: no real charges. Upgrade flows are simulated.",
    }


@router.post("/payments/checkout")
async def checkout(
    data: dict,
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    plan = str(data.get("plan", "pro")).lower()
    if plan not in SANDBOX_PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown plan '{plan}'. Available: {sorted(SANDBOX_PLANS)}.",
        )
    # Card details (cardNumber/cardExpiry/cardCvc) are intentionally ignored:
    # sandbox mode performs no charge and stores nothing.
    logger.info("sandbox_checkout", plan=plan)
    return {
        "mode": "sandbox",
        "status": "success",
        "plan": plan,
        "amount_charged": 0,
        "message": f"Sandbox checkout complete for the '{plan}' plan — no real charge was made.",
    }


@router.post("/payments/downgrade")
async def downgrade(
    data: dict,
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    logger.info("sandbox_downgrade")
    return {
        "mode": "sandbox",
        "status": "success",
        "plan": "free",
        "message": "Sandbox downgrade complete — plan set to 'free'. No real billing change.",
    }

# ---------------------------------------------------------------------------
# Digital Twin - Topology
# ---------------------------------------------------------------------------

def _classify_assets(assets):
    """Split assets into (db_servers, web_servers, workstations) by type."""
    db_servers, web_servers, workstations = [], [], []
    for a in assets:
        atype = (a.asset_type or "").lower()
        if "database" in atype or "db" in atype:
            db_servers.append(a.hostname)
        elif "web" in atype:
            web_servers.append(a.hostname)
        else:
            workstations.append(a.hostname)
    return db_servers, web_servers, workstations


def _build_graph(assets):
    """Build (nodes, edges, adjacency, db_servers) for the asset topology.

    Directed CONNECTS_TO edges: workstations -> web servers -> databases.
    """
    nodes = []
    for a in assets:
        nodes.append({
            "id": a.hostname,
            "label": a.asset_type.split(" ")[0] if a.asset_type else "Host",
            "properties": {
                "ip": a.ip_address,
                "criticality": a.criticality.value if a.criticality else "Medium",
            },
        })

    db_servers, web_servers, workstations = _classify_assets(assets)
    edges = []
    adjacency = defaultdict(list)
    edge_id = 1

    def add_edge(src, tgt, proto):
        nonlocal edge_id
        edges.append({
            "id": f"e{edge_id}", "source": src, "target": tgt,
            "type": "CONNECTS_TO", "properties": {"protocol": proto},
        })
        adjacency[src].append(tgt)
        edge_id += 1

    for w in workstations:
        for web in web_servers:
            add_edge(w, web, "HTTPS")
    for web in web_servers:
        for db_srv in db_servers:
            add_edge(web, db_srv, "TCP/5432")

    return nodes, edges, adjacency, db_servers


@router.get("/digital_twin/topology")
async def get_topology(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset))
    assets = result.scalars().all()

    nodes, edges, _, _ = _build_graph(assets)

    logger.info("topology_fetched", node_count=len(nodes), edge_count=len(edges))
    return {"nodes": nodes, "edges": edges}

@router.post("/digital_twin/simulate")
async def simulate(data: dict, db: AsyncSession = Depends(get_db)):
    node_id = data.get("node_id", "")
    attack_type = data.get("attack_type", "RANSOMWARE")
    risk_factor = data.get("risk_factor", 0.5)

    result = await db.execute(select(Asset))
    assets = result.scalars().all()

    affected_nodes = [{"id": node_id}]
    affected_edges = []
    db_servers, web_servers, workstations = [], [], []

    for a in assets:
        atype = (a.asset_type or "").lower()
        if "database" in atype or "db" in atype:
            db_servers.append(a.hostname)
        elif "web" in atype:
            web_servers.append(a.hostname)
        else:
            workstations.append(a.hostname)

    if node_id in workstations:
        for web in web_servers:
            affected_nodes.append({"id": web})
            affected_edges.append({"source": node_id, "target": web, "probability": risk_factor * 0.8})
            for db_srv in db_servers:
                affected_nodes.append({"id": db_srv})
                affected_edges.append({"source": web, "target": db_srv, "probability": risk_factor * 0.6})
    elif node_id in web_servers:
        for db_srv in db_servers:
            affected_nodes.append({"id": db_srv})
            affected_edges.append({"source": node_id, "target": db_srv, "probability": risk_factor * 0.9})

    unique_nodes = {n["id"]: n for n in affected_nodes}.values()
    logger.info("simulation_complete", attack_type=attack_type, node_id=node_id, blast_radius=min(risk_factor * 1.5, 0.99))
    return {
        "status": "success",
        "blast_radius_score": min(risk_factor * 1.5, 0.99),
        "critical_assets_at_risk": len(db_servers),
        "affected_nodes": list(unique_nodes),
        "affected_edges": affected_edges,
    }

@router.get("/digital_twin/blast-radius")
async def get_blast_radius(
    node_id: str = Query(...),
    node_label: str = Query("Host"),
    max_hops: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """BFS blast-radius from a compromised node over the asset topology."""
    result = await db.execute(select(Asset))
    assets = result.scalars().all()
    nodes, edges, adjacency, db_servers = _build_graph(assets)

    node_ids = {n["id"] for n in nodes}
    if node_id not in node_ids:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in topology.")

    reached = {node_id: 0}
    queue = deque([node_id])
    while queue:
        cur = queue.popleft()
        if reached[cur] >= max_hops:
            continue
        for nxt in adjacency.get(cur, []):
            if nxt not in reached:
                reached[nxt] = reached[cur] + 1
                queue.append(nxt)

    reached_nodes = [n for n in nodes if n["id"] in reached]
    reached_edges = [e for e in edges if e["source"] in reached and e["target"] in reached]
    critical_reached = [h for h in db_servers if h in reached]
    score = round(len(reached) / len(nodes), 2) if nodes else 0.0

    logger.info("blast_radius_computed", node_id=node_id, reached=len(reached), score=score)
    return {
        "node_id": node_id,
        "node_label": node_label,
        "max_hops": max_hops,
        "nodes": reached_nodes,
        "edges": reached_edges,
        "nodes_affected": len(reached),
        "critical_assets_reached": critical_reached,
        "blast_radius_score": score,
        "model": "heuristic-bfs-v1",
    }

@router.get("/digital_twin/attack-paths")
async def get_attack_paths(
    from_id: str = Query(...),
    to_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """All shortest attack paths from one node to another (BFS, capped at 25)."""
    result = await db.execute(select(Asset))
    assets = result.scalars().all()
    nodes, edges, adjacency, _ = _build_graph(assets)

    node_ids = {n["id"] for n in nodes}
    if from_id not in node_ids:
        raise HTTPException(status_code=404, detail=f"Node '{from_id}' not found in topology.")
    if to_id not in node_ids:
        raise HTTPException(status_code=404, detail=f"Node '{to_id}' not found in topology.")

    # BFS distances from from_id
    dist = {from_id: 0}
    queue = deque([from_id])
    while queue:
        cur = queue.popleft()
        for nxt in adjacency.get(cur, []):
            if nxt not in dist:
                dist[nxt] = dist[cur] + 1
                queue.append(nxt)

    if to_id not in dist:
        return {"from_id": from_id, "to_id": to_id, "paths": [], "path_count": 0,
                "shortest_hops": None, "message": "No path exists between the nodes."}

    # DFS enumerating shortest paths only
    paths = []
    shortest = dist[to_id]

    def dfs(cur, path):
        if len(paths) >= 25:
            return
        if cur == to_id:
            paths.append(list(path))
            return
        for nxt in adjacency.get(cur, []):
            if dist.get(nxt) == dist[cur] + 1 and nxt not in path:
                path.append(nxt)
                dfs(nxt, path)
                path.pop()

    dfs(from_id, [from_id])
    logger.info("attack_paths_computed", from_id=from_id, to_id=to_id, count=len(paths))
    return {
        "from_id": from_id,
        "to_id": to_id,
        "paths": paths,
        "path_count": len(paths),
        "shortest_hops": shortest,
    }

@router.delete("/digital_twin/cleanup")
async def cleanup(
    sim_id: str = Query(None),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    logger.info("digital_twin_cleanup", sim_id=sim_id)
    return {
        "status": "success",
        "cleaned": 0,
        "message": "Simulations are computed on-demand and nothing is persisted; nothing to clean.",
    }

# ---------------------------------------------------------------------------
# Executive Metrics
# ---------------------------------------------------------------------------

@router.get("/executive/metrics")
async def executive_metrics(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Executive metrics in the flat shape the frontend dashboard consumes.

    Counts are tenant-scoped and computed from the database. Scores are
    labeled derived heuristics ("derived-heuristic-v1"), not ML output.
    trend/target series are empty until timeseries data exists.
    """
    tenant_id = current_tenant_id.get() or 1
    open_statuses = [StatusEnum.OPEN, StatusEnum.IN_PROGRESS]
    closed_statuses = [StatusEnum.RESOLVED, StatusEnum.CLOSED]

    async def _count(model, *clauses):
        return (await db.execute(
            select(func.count(model.id)).where(model.tenant_id == tenant_id, *clauses)
        )).scalar() or 0

    open_inc = await _count(Incident, Incident.status.in_(open_statuses))
    resolved_inc = await _count(Incident, Incident.status.in_(closed_statuses))
    total_alerts = await _count(Alert)
    crit_open = await _count(
        Incident, Incident.status.in_(open_statuses), Incident.severity == SeverityEnum.CRITICAL)
    high_open = await _count(
        Incident, Incident.status.in_(open_statuses), Incident.severity == SeverityEnum.HIGH)
    crit_assets = await _count(
        Asset, Asset.criticality.in_([CriticalityEnum.CRITICAL, CriticalityEnum.HIGH]))
    total_assets = await _count(Asset)

    # MTTR from resolved incidents' open duration; 0 when nothing resolved yet.
    mttr_hours = 0.0
    if resolved_inc:
        rows = (await db.execute(
            select(Incident.created_at, Incident.updated_at).where(
                Incident.tenant_id == tenant_id, Incident.status.in_(closed_statuses))
        )).all()
        durs = [(u - c).total_seconds() / 3600 for c, u in rows if c and u and u > c]
        if durs:
            mttr_hours = round(sum(durs) / len(durs), 2)

    posture_score = max(0, 100 - (crit_open * 15 + high_open * 8 + open_inc * 2))
    asset_risk_score = round(100 * crit_assets / total_assets, 1) if total_assets else 0.0

    if open_inc == 0 and total_alerts == 0:
        summary = ("No open incidents and no ingested alerts for this tenant. "
                   "Posture is nominal; connect an alert source to begin monitoring.")
    else:
        summary = (f"{open_inc} open incident(s) ({crit_open} critical, {high_open} high), "
                   f"{resolved_inc} resolved, {total_alerts} alert(s) ingested. "
                   f"Mean time to resolve is {mttr_hours}h.")

    return {
        "posture_score": posture_score,
        "mttr_hours": mttr_hours,
        "mttd_hours": 0.0,
        "open_incidents": open_inc,
        "resolved_incidents": resolved_inc,
        "total_alerts": total_alerts,
        "asset_risk_score": asset_risk_score,
        "executive_summary": summary,
        "threat_trends": [],
        "top_targets": [],
        "score_basis": "derived-heuristic-v1",
    }

# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------

def _validate_block_ip(raw: str) -> str:
    """Pentest MEDIUM-1: a firewall block target must be a real, routable IP.

    Rejects garbage ("999.999.999.999") and non-routable targets (loopback,
    link-local, multicast, unspecified, reserved) that must never ship to
    sensors. Private LAN ranges stay allowed (internal segmentation).
    """
    text = (raw or "").strip()
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid IP address")
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        raise HTTPException(status_code=400, detail="IP is not a routable block target")
    return str(ip)


@router.get("/firewall/blocks")
async def get_firewall_blocks(_auth=Depends(require_roles_dual(READ_ROLES))):
    return []

@router.post("/firewall/block")
async def block_ip(data: dict, _auth=Depends(require_roles_dual(WRITE_ROLES))):
    ip = _validate_block_ip(str(data.get("ip", "")))
    logger.info("firewall_block_ip", ip=ip)
    return {"status": "success", "ip": ip}

@router.post("/firewall/unblock")
async def unblock_ip(data: dict, _auth=Depends(require_roles_dual(WRITE_ROLES))):
    ip = _validate_block_ip(str(data.get("ip", "")))
    logger.info("firewall_unblock_ip", ip=ip)
    return {"status": "success", "ip": ip}

# ---------------------------------------------------------------------------
# Threat Intelligence
# ---------------------------------------------------------------------------

@router.get("/threat-intel/cve/{cve}")
async def cve_intel(cve: str):
    logger.info("threat_intel_cve_lookup", cve=cve)
    return {"cve": cve, "intel": "No data"}

@router.get("/threat-intel/ip/{ip}")
async def ip_intel(ip: str):
    logger.info("threat_intel_ip_lookup", ip=ip)
    return {"ip": ip, "intel": "No data"}

@router.post("/threat-intel/sync")
async def sync_ti():
    logger.info("threat_intel_sync")
    return {"status": "success"}

@router.post("/threat-intel/kev/sync")
async def sync_kev():
    logger.info("kev_sync")
    return {"status": "success"}

# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

@router.get("/integrations/status")
async def integrations_status():
    return []

@router.post("/integrations/sync")
async def sync_integrations():
    logger.info("integrations_sync")
    return {"status": "success"}
