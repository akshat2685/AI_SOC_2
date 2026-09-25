import structlog
import httpx
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
    Playbook, RoleEnum, ApprovalStatusEnum,
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

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="AI Copilot is not configured: set GEMINI_API_KEY in the backend environment and redeploy.",
        )
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
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": query + context_block}]}],
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
                },
            )
    except httpx.HTTPError as e:
        logger.error("chat_upstream_unreachable", error=str(e))
        raise HTTPException(status_code=502, detail="AI provider unreachable; try again shortly.")

    if resp.status_code == 404:
        raise HTTPException(
            status_code=502,
            detail=f"Model '{model}' is not available for this API key; set GEMINI_MODEL to a supported model.",
        )
    if resp.status_code != 200:
        logger.error("chat_provider_error", status=resp.status_code, body=resp.text[:500])
        raise HTTPException(status_code=502, detail="AI provider returned an error; try again shortly.")

    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="AI provider returned an unreadable response.")

    logger.info("chat_answered", model=model, query_len=len(query))
    return {"response": text, "model": model}

# ---------------------------------------------------------------------------
# MITRE ATT&CK
# ---------------------------------------------------------------------------

@router.get("/mitre/mappings")
async def get_mitre_mappings(
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Curated MITRE ATT&CK Enterprise subset + rule-pattern mappings.

    This is a static, curated subset (not the full ATT&CK dataset) so the
    endpoint works with zero external dependencies.
    """
    techniques = [
        {"id": "T1059", "name": "Command and Scripting Interpreter", "tactic": "Execution",
         "description": "Adversaries abuse command-line interpreters (PowerShell, cmd, bash) to execute commands and payloads."},
        {"id": "T1059.001", "name": "PowerShell", "tactic": "Execution",
         "description": "Adversaries use PowerShell to execute commands, download payloads, and evade defenses."},
        {"id": "T1078", "name": "Valid Accounts", "tactic": "Persistence",
         "description": "Adversaries obtain and abuse credentials of existing accounts to gain and keep access."},
        {"id": "T1078.002", "name": "Valid Accounts: Domain Accounts", "tactic": "Persistence",
         "description": "Compromised domain credentials used for lateral movement and persistence."},
        {"id": "T1110", "name": "Brute Force", "tactic": "Credential Access",
         "description": "Repeated authentication attempts to guess credentials."},
        {"id": "T1110.001", "name": "Brute Force: Password Guessing", "tactic": "Credential Access",
         "description": "Password guessing against login services such as SSH, RDP, or web apps."},
        {"id": "T1133", "name": "External Remote Services", "tactic": "Persistence",
         "description": "Use of external remote services (VPN, RDP, SSH) for persistent access."},
        {"id": "T1021", "name": "Remote Services", "tactic": "Lateral Movement",
         "description": "Use of remote services (RDP, SMB, WinRM, SSH) to move laterally."},
        {"id": "T1021.004", "name": "Remote Services: SSH", "tactic": "Lateral Movement",
         "description": "SSH used for lateral movement between hosts."},
        {"id": "T1486", "name": "Data Encrypted for Impact", "tactic": "Impact",
         "description": "Ransomware-style encryption of data to disrupt availability."},
        {"id": "T1490", "name": "Inhibit System Recovery", "tactic": "Impact",
         "description": "Deletion or disabling of backups and recovery mechanisms (e.g. shadow copies)."},
        {"id": "T1041", "name": "Exfiltration Over C2 Channel", "tactic": "Exfiltration",
         "description": "Data stolen over an existing command-and-control channel."},
        {"id": "T1048", "name": "Exfiltration Over Alternative Protocol", "tactic": "Exfiltration",
         "description": "Exfiltration over DNS, ICMP, or other non-standard protocols."},
        {"id": "T1071", "name": "Application Layer Protocol", "tactic": "Command and Control",
         "description": "C2 communication over common protocols (HTTP/S, DNS) to blend in."},
        {"id": "T1071.001", "name": "Application Layer Protocol: Web Protocols", "tactic": "Command and Control",
         "description": "C2 over HTTP/S to attacker-controlled infrastructure."},
        {"id": "T1105", "name": "Ingress Tool Transfer", "tactic": "Command and Control",
         "description": "Download of tools/payloads to the victim (curl, wget, certutil, bitsadmin)."},
        {"id": "T1055", "name": "Process Injection", "tactic": "Defense Evasion",
         "description": "Code injected into legitimate processes to evade detection."},
        {"id": "T1036", "name": "Masquerading", "tactic": "Defense Evasion",
         "description": "Malicious binaries renamed to look like legitimate system files."},
        {"id": "T1003", "name": "OS Credential Dumping", "tactic": "Credential Access",
         "description": "Dumping credentials from LSASS, SAM, or /etc/shadow (e.g. Mimikatz)."},
        {"id": "T1003.001", "name": "OS Credential Dumping: LSASS Memory", "tactic": "Credential Access",
         "description": "Credential material extracted from LSASS process memory."},
        {"id": "T1083", "name": "File and Directory Discovery", "tactic": "Discovery",
         "description": "Enumerating files and directories to find data of interest."},
        {"id": "T1018", "name": "Remote System Discovery", "tactic": "Discovery",
         "description": "Scanning the network to discover reachable remote systems."},
        {"id": "T1595", "name": "Active Scanning", "tactic": "Reconnaissance",
         "description": "Probing victim infrastructure (port scans, vulnerability scans)."},
        {"id": "T1190", "name": "Exploit Public-Facing Application", "tactic": "Initial Access",
         "description": "Exploiting internet-facing apps (web servers, VPN appliances)."},
        {"id": "T1566", "name": "Phishing", "tactic": "Initial Access",
         "description": "Phishing emails/links delivering malware or harvesting credentials."},
    ]
    rule_mappings = [
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
    return {
        "techniques": techniques,
        "rule_mappings": rule_mappings,
        "count": len(techniques),
        "source": "curated-subset",
        "note": "Curated subset of MITRE ATT&CK Enterprise for offline use; not the full dataset.",
    }

# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(AuditEvent).order_by(desc(AuditEvent.id)).offset(skip).limit(limit)
        )
        events = result.scalars().all()
        logger.info("audit_log_listed", count=len(events))
        return events
    except Exception as e:
        logger.error("audit_log_failed", error=str(e))
        return []

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
    await db.commit()
    logger.info("approval_approved", approval_id=approval_id, tenant_id=tenant_id)
    return {"status": "success", "id": ar.id, "new_status": "APPROVED"}


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
async def executive_metrics(db: AsyncSession = Depends(get_db)):
    try:
        inc_count = (await db.execute(select(func.count(Incident.id)))).scalar() or 0
        alert_count = (await db.execute(select(func.count(Alert.id)))).scalar() or 0
    except Exception:
        inc_count = 0
        alert_count = 0
    return {"metrics": {"total_incidents": inc_count, "total_alerts": alert_count}}

# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------

@router.get("/firewall/blocks")
async def get_firewall_blocks():
    return []

@router.post("/firewall/block")
async def block_ip(data: dict):
    ip = data.get("ip", "")
    logger.info("firewall_block_ip", ip=ip)
    return {"status": "success", "ip": ip}

@router.post("/firewall/unblock")
async def unblock_ip(data: dict):
    ip = data.get("ip", "")
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
