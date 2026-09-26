#!/usr/bin/env python3
"""EDYSOR reference endpoint sensor — Linux/macOS/Windows, user-space.

Collects process, network, file-integrity and auth events on the local machine
and ships them to the EDYSOR backend event-ingestion API:

    POST {backend_url}/api/v1/events/ingest
    X-API-Key: <api_key>
    {"device_id": "agt-<hex>", "events": [ ... ]}

First run registers the device automatically:
    POST {backend_url}/api/v1/agents/register
    {"hostname", "platform": "linux|macos|windows", "os_version", "arch",
     "agent_version": "0.1.0"}
and stores the returned device_id in the config file.

Windows notes:
  * Process/network/file collectors use psutil and work on Windows as-is.
  * Windows Event Log (Security channel: logons 4624/4625, process creation
    4688, user creation 4720) needs the optional `pywin32` package AND
    administrator privileges (the Security log is admin-only). Without either,
    event-log collection is skipped with a logged warning — never silently.
  * Registry Run-key persistence (HKCU/HKLM ...\\CurrentVersion\\Run) is
    polled via stdlib `winreg`; reported as file-type events with the key
    path as `file.path`.
  * StringInserts indices in event-log parsing are best-effort (they vary
    across Windows builds); unparseable fields are sent as null, never
    invented.

Honesty notes (read before trusting its output):
  * This is a USER-SPACE, POLLING sensor. It sees a snapshot every
    `interval_seconds`; short-lived processes that start and exit between two
    polls are MISSED (on Windows, Event ID 4688 closes much of this gap when
    process-creation auditing is enabled). It is not a kernel hook / ETW
    consumer.
  * Fields it cannot observe are sent as JSON null, never invented.
    (e.g. per-connection byte counters, the PID that wrote a file.)
  * `severity_hint` is a small documented HEURISTIC, not a detection verdict.
  * DNS capture is intentionally NOT implemented (needs pcap/admin).
  * macOS auth-log parsing is intentionally NOT implemented (unified logging
    needs special entitlements); Linux parses /var/log/auth.log best-effort.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import logging
import os
import platform
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover
    print("ERROR: the 'psutil' package is required: pip install -r requirements.txt",
          file=sys.stderr)
    sys.exit(2)

try:
    import requests
except ImportError:  # pragma: no cover
    print("ERROR: the 'requests' package is required: pip install -r requirements.txt",
          file=sys.stderr)
    sys.exit(2)

AGENT_VERSION = "0.1.0"
DEFAULT_INTERVAL = 30
SPOOL_NAME = "spool.jsonl"
CONFIG_NAME = "sensor.json"
HASH_CHUNK = 65536

# Watch paths are platform-specific: persistence / integrity locations an
# attacker touches. TEMP-style directories are deliberately excluded (noise).
_WATCH_PATHS = {
    "linux": ["/etc/crontab", "/etc/cron.d", "~/.ssh/authorized_keys"],
    "macos": ["/etc/crontab", "~/.ssh/authorized_keys"],
    "windows": [
        r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup",
        r"%SystemRoot%\System32\drivers\etc\hosts",
    ],
}


def default_watch_paths() -> list[str]:
    """Integrity watch list for the current platform."""
    if sys.platform == "win32":
        return list(_WATCH_PATHS["windows"])
    if sys.platform == "darwin":
        return list(_WATCH_PATHS["macos"])
    return list(_WATCH_PATHS["linux"])

log = logging.getLogger("edysor_sensor")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def default_config_path() -> Path:
    return Path.home() / ".config" / "edysor" / CONFIG_NAME


def default_spool_path(config_path: Path) -> Path:
    return config_path.parent / SPOOL_NAME


def load_config(path: Path) -> dict:
    cfg = {
        "backend_url": "",
        "api_key": "",
        "device_id": "",
        "interval_seconds": DEFAULT_INTERVAL,
        "watch_paths": default_watch_paths(),
        "auth_log_offset": 0,
    }
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read config %s (%s); using defaults", path, exc)
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Config holds an API key: restrict permissions.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Platform / identity
# --------------------------------------------------------------------------- #

def detect_platform() -> str:
    """Map sys.platform to the backend's platform enum. Exits on unsupported OS."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "win32":
        return "windows"
    print(f"ERROR: unsupported platform '{sys.platform}' (linux, macos, windows only)",
          file=sys.stderr)
    sys.exit(2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str) -> str | None:
    """Best-effort SHA-256. Returns None (honest null) when unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(HASH_CHUNK), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def register_device(cfg: dict, config_path: Path) -> bool:
    """Register with the backend; store device_id in config. Returns success."""
    url = cfg["backend_url"].rstrip("/") + "/api/v1/agents/register"
    payload = {
        "hostname": socket.gethostname(),
        "platform": detect_platform(),
        "os_version": platform.platform(),
        "arch": platform.machine(),
        "agent_version": AGENT_VERSION,
    }
    try:
        resp = requests.post(url, json=payload,
                             headers={"X-API-Key": cfg["api_key"]},
                             timeout=15)
    except requests.RequestException as exc:
        log.error("registration failed: cannot reach backend (%s)", exc)
        return False
    if resp.status_code >= 400:
        log.error("registration failed: HTTP %s: %s", resp.status_code,
                  resp.text[:300])
        return False
    try:
        body = resp.json()
        # Backend returns {"device_identity": {"device_id": ...}, "note": ...};
        # accept a flat {"device_id": ...} too for forward-compat.
        device_id = (body.get("device_identity") or {}).get("device_id") \
            or body.get("device_id")
        if not device_id:
            raise KeyError("device_id")
    except (ValueError, KeyError) as exc:
        log.error("registration failed: unexpected response (%s): %s",
                  exc, resp.text[:300])
        return False
    cfg["device_id"] = device_id
    save_config(config_path, cfg)
    log.info("registered as device %s", device_id)
    return True


# --------------------------------------------------------------------------- #
# Severity heuristics
# --------------------------------------------------------------------------- #
# HEURISTIC — not a detection verdict. These hints help analysts triage; they
# WILL produce false positives (e.g. an admin running curl). The backend's ML
# models do the real scoring; this field is just a first-pass hint.
# Keep this list small and explicit; document every rule here.

SUSPICIOUS_CMDLINE = re.compile(
    r"(^|[\s;/\\])"                       # token boundary
    r"(curl|wget|nc|ncat|nmap|base64|xxd|powershell|pwsh|mimikatz)"
    r"([\s;]|$)"                          # token boundary
    r"|/dev/tcp/"                         # bash reverse-shell idiom
    r"|base64\s+(-d|--decode)",           # decode-and-execute pattern
    re.IGNORECASE,
)


def is_public_ip(ip: str) -> bool | None:
    """True if routable public IP, False if private/loopback/link-local,
    None if unparseable."""
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_loopback or addr.is_link_local or addr.is_multicast:
            return False
        return not addr.is_private
    except ValueError:
        return None


def hint_for_process(cmdline: str) -> str:
    if cmdline and SUSPICIOUS_CMDLINE.search(cmdline):
        return "medium"
    return "info"


def hint_for_network(dst_ip: str) -> str:
    public = is_public_ip(dst_ip)
    if public is True:
        return "low"      # outbound to the public internet: worth a glance
    return "info"


def hint_for_file() -> str:
    # Any change under the watched integrity paths is high-interest.
    return "high"


def hint_for_auth(action: str, result: str) -> str:
    if action == "failed_login":
        return "medium"
    if action in ("login", "sudo", "ssh"):
        return "low"
    return "info"


# --------------------------------------------------------------------------- #
# Collectors
# --------------------------------------------------------------------------- #

class CollectorState:
    """In-memory baselines so we emit diffs, not full snapshots."""

    def __init__(self) -> None:
        self.pids: set[int] = set()
        self.pid_names: dict[int, str] = {}
        self.baselined_processes = False
        self.conns: set[tuple] = set()
        self.file_state: dict[str, tuple[float, int]] = {}
        self.baselined_files = False
        # Windows Event Log: highest record number seen (baseline on 1st run).
        self.win_event_record: int = 0
        self.win_eventlog_baselined = False
        self.win_eventlog_warned = False
        # Windows Run-key persistence: {key_path: {value_name: value_data}}.
        self.run_values: dict[str, dict[str, str]] = {}
        self.run_baselined = False


def collect_processes(state: CollectorState) -> list[dict]:
    """Emit one event per NEW process since the last poll.

    Limitation: processes that start AND exit between two polls are missed
    (polling, not event-driven). First call only establishes the baseline.
    """
    events: list[dict] = []
    current_pids: set[int] = set()
    pid_names: dict[int, str] = {}
    try:
        procs = list(psutil.process_iter(
            ["pid", "ppid", "name", "exe", "cmdline", "username", "create_time"]))
    except Exception as exc:  # psutil can raise on exotic /proc entries
        log.warning("process snapshot failed: %s", exc)
        return events

    for p in procs:
        info = p.info
        pid = info.get("pid")
        if pid is None:
            continue
        current_pids.add(pid)
        name = info.get("name") or ""
        pid_names[pid] = name

        if not state.baselined_processes or pid in state.pids:
            continue  # baseline pass, or already-seen process

        cmdline_list = info.get("cmdline") or []
        cmdline = " ".join(cmdline_list)
        exe = info.get("exe") or ""
        try:
            started = datetime.fromtimestamp(info["create_time"], tz=timezone.utc).isoformat()
        except (KeyError, TypeError, OSError, OverflowError):
            started = None
        events.append({
            "event_type": "process",
            "observed_at": now_iso(),
            "severity_hint": hint_for_process(cmdline),
            "process": {
                "pid": pid,
                "ppid": info.get("ppid"),
                "name": name,
                "exe": exe or None,
                "cmdline": cmdline_list,          # list: faithful, unjoined
                "user": info.get("username"),
                "started_at": started,            # null when unknowable
                "hash_sha256": sha256_file(exe) if exe else None,
            },
        })

    state.pids = current_pids
    state.pid_names = pid_names
    state.baselined_processes = True
    return events


def _conn_key(conn) -> tuple:
    laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
    raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
    return (conn.pid, conn.type, laddr, raddr, conn.status)


def collect_network(state: CollectorState) -> list[dict]:
    """Emit one event per NEW socket since the last poll.

    Loopback sockets are skipped (noise). bytes_sent/bytes_recv are NOT
    available from psutil and are sent as honest nulls.
    """
    events: list[dict] = []
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, RuntimeError) as exc:
        log.warning("network snapshot failed (try running as root): %s", exc)
        return events

    for conn in conns:
        if not conn.raddr:
            continue  # listening socket or unconnected: skip (noise)
        try:
            if ipaddress.ip_address(conn.raddr.ip).is_loopback:
                continue
        except ValueError:
            continue
        key = _conn_key(conn)
        if key in state.conns:
            continue
        state.conns.add(key)
        if len(state.conns) > 20000:  # bounded memory; old entries re-emit
            state.conns.clear()

        proto = "tcp" if conn.type == socket.SOCK_STREAM else (
            "udp" if conn.type == socket.SOCK_DGRAM else str(conn.type))
        pid = conn.pid
        events.append({
            "event_type": "network",
            "observed_at": now_iso(),
            "severity_hint": hint_for_network(conn.raddr.ip),
            "network": {
                "pid": pid,
                "process_name": state.pid_names.get(pid),
                "src_ip": conn.laddr.ip if conn.laddr else None,
                "src_port": conn.laddr.port if conn.laddr else None,
                "dst_ip": conn.raddr.ip,
                "dst_port": conn.raddr.port,
                "proto": proto,
                "direction": "outbound",
                "bytes_sent": None,   # not observable via psutil: honest null
                "bytes_recv": None,   # not observable via psutil: honest null
            },
        })
    return events


def expand_watch_paths(raw_paths: list[str]) -> list[str]:
    """Expand ~ and env vars; also expand one directory level so that watching
    a directory (e.g. /etc/cron.d) covers the files inside it."""
    paths: list[str] = []
    for raw in raw_paths:
        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        if p.is_dir():
            try:
                paths.extend(str(child) for child in p.iterdir())
            except OSError:
                continue
        else:
            paths.append(str(p))
    return paths


def collect_files(state: CollectorState, watch_paths: list[str]) -> list[dict]:
    """Poll watched paths for created/modified/deleted. First call baselines.

    Limitation: polling, not inotify — changes between polls are coalesced,
    and the writing process is UNKNOWN (pid/process_name sent as null).
    """
    events: list[dict] = []
    current: dict[str, tuple[float, int]] = {}
    for spath in expand_watch_paths(watch_paths):
        try:
            st = os.stat(spath)
        except OSError:
            continue  # missing or unreadable: skip silently
        current[spath] = (st.st_mtime, st.st_size)

    if not state.baselined_files:
        state.file_state = current
        state.baselined_files = True
        return events  # baseline pass: no events on startup

    for spath, (mtime, size) in current.items():
        old = state.file_state.get(spath)
        action = None
        if old is None:
            action = "created"
        elif old != (mtime, size):
            action = "modified"
        if action:
            events.append({
                "event_type": "file",
                "observed_at": now_iso(),
                "severity_hint": hint_for_file(),
                "file": {
                    "path": spath,
                    "action": action,
                    "hash_sha256": sha256_file(spath),
                    "pid": None,            # unknown via polling: honest null
                    "process_name": None,   # unknown via polling: honest null
                },
            })
    for spath in state.file_state:
        if spath not in current:
            events.append({
                "event_type": "file",
                "observed_at": now_iso(),
                "severity_hint": hint_for_file(),
                "file": {
                    "path": spath,
                    "action": "deleted",
                    "hash_sha256": None,
                    "pid": None,
                    "process_name": None,
                },
            })
    state.file_state = current
    return events


# Linux auth.log parsing (best-effort). macOS unified log needs entitlements:
# intentionally not implemented — see module docstring.
AUTH_PATTERNS = [
    (re.compile(r"Failed password for (?:invalid user )?(\S+) from (\S+)"),
     "failed_login", "failure"),
    (re.compile(r"Accepted (?:password|publickey) for (\S+) from (\S+)"),
     "login", "success"),
    (re.compile(r"session opened for user (\S+).*by (\S+)"),
     "login", "success"),
    (re.compile(r"session closed for user (\S+)"),
     "logout", "success"),
    (re.compile(r"sudo:\s+(\S+)\s*:.*COMMAND="),
     "sudo", "success"),
]


def collect_auth(state: CollectorState, cfg: dict, config_path: Path) -> list[dict]:
    """Tail /var/log/auth.log (Linux only) for new lines since last offset."""
    events: list[dict] = []
    if sys.platform != "linux":
        return events
    log_path = Path("/var/log/auth.log")
    try:
        size = log_path.stat().st_size
    except OSError:
        return events  # missing/unreadable: skip silently
    offset = cfg.get("auth_log_offset", 0) or 0
    if offset > size:
        offset = 0  # log rotated
    try:
        with open(log_path, "rb") as fh:
            fh.seek(offset)
            data = fh.read().decode("utf-8", errors="replace")
            new_offset = fh.tell()
    except OSError:
        return events
    for line in data.splitlines()[-500:]:  # bound work per interval
        for pattern, action, result in AUTH_PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            user = m.group(1)
            src_ip = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            if src_ip and not re.fullmatch(r"[\d.:a-fA-F]+", src_ip or ""):
                src_ip = None
            events.append({
                "event_type": "auth",
                "observed_at": now_iso(),
                "severity_hint": hint_for_auth(action, result),
                "auth": {
                    "user": user,
                    "action": action,
                    "src_ip": src_ip,
                    "result": result,
                },
            })
            break
    if new_offset != offset:
        cfg["auth_log_offset"] = new_offset
        try:
            save_config(config_path, cfg)
        except OSError as exc:
            log.warning("could not persist auth offset: %s", exc)
    return events


# --------------------------------------------------------------------------- #
# Windows collectors (win32 only; everything import-gated and best-effort)
# --------------------------------------------------------------------------- #

# Security-channel Event IDs we care about. StringInserts layouts vary across
# Windows builds — every index below is guarded; unknown fields become null.
_WIN_EVENT_IDS = {4624, 4625, 4688, 4720, 4672}


def _win32evtlog():
    try:
        import win32evtlog
        return win32evtlog
    except ImportError:
        return None


def _inserts(ev, idx: int) -> str | None:
    """Best-effort StringInserts lookup; None when absent/unparseable."""
    try:
        inserts = ev.StringInserts
        if inserts and 0 <= idx < len(inserts):
            val = inserts[idx]
            return str(val) if val is not None else None
    except Exception:
        pass
    return None


def _evt_time_utc(ev) -> str:
    try:
        return ev.TimeGenerated.astimezone(timezone.utc).isoformat()
    except Exception:
        return now_iso()


def collect_win_events(state: CollectorState) -> list[dict]:
    """Read new Security-log events (logons, process creation, user mgmt).

    Requires pywin32 AND admin rights (Security log is admin-only). Event
    4688 closes the polling gap for short-lived processes when process
    auditing is enabled — otherwise it simply yields nothing.
    """
    events: list[dict] = []
    if sys.platform != "win32":
        return events
    w32 = _win32evtlog()
    if w32 is None:
        if not state.win_eventlog_warned:
            log.warning("pywin32 not installed — Windows Event Log collection "
                        "disabled (pip install pywin32 for logon/process telemetry)")
            state.win_eventlog_warned = True
        return events

    hand = None
    try:
        hand = w32.OpenEventLog(None, "Security")
    except Exception as exc:
        if not state.win_eventlog_warned:
            log.warning("cannot open Security event log (run as administrator "
                        "for logon/process telemetry): %s", exc)
            state.win_eventlog_warned = True
        return events

    try:
        flags = w32.EVENTLOG_BACKWARDS_READ | w32.EVENTLOG_SEQUENTIAL_READ
        newest = state.win_event_record
        pending: list = []
        # Newest-first; stop at the first record we have already seen.
        # Bound total work per cycle so a huge backlog can't stall us.
        for _ in range(10):  # <= ~10 chunks per cycle
            try:
                chunk = w32.ReadEventLog(hand, flags, 0)
            except Exception as exc:
                log.warning("event log read failed: %s", exc)
                break
            if not chunk:
                break
            done = False
            for ev in chunk:
                rec = ev.RecordNumber
                if rec > newest:
                    newest = rec
                if rec <= state.win_event_record:
                    done = True
                    break
                pending.append(ev)
                if len(pending) >= 300:
                    done = True
                    break
            if done:
                break

        if not state.win_eventlog_baselined:
            # First run: establish the high-water mark, emit nothing (no
            # flooding the backend with history).
            state.win_event_record = newest
            state.win_eventlog_baselined = True
            return events

        for ev in reversed(pending):  # chronological order
            eid = ev.EventID & 0xFFFF
            if eid not in _WIN_EVENT_IDS:
                continue
            observed = _evt_time_utc(ev)
            if eid == 4625:  # failed logon
                events.append({
                    "event_type": "auth", "observed_at": observed,
                    "severity_hint": hint_for_auth("failed_login", "failure"),
                    "auth": {"user": _inserts(ev, 5), "action": "failed_login",
                             "src_ip": _inserts(ev, 19), "result": "failure"},
                })
            elif eid == 4624:  # successful logon
                events.append({
                    "event_type": "auth", "observed_at": observed,
                    "severity_hint": hint_for_auth("login", "success"),
                    "auth": {"user": _inserts(ev, 5), "action": "login",
                             "src_ip": _inserts(ev, 18), "result": "success"},
                })
            elif eid == 4720:  # user account created
                events.append({
                    "event_type": "auth", "observed_at": observed,
                    "severity_hint": "medium",
                    "auth": {"user": _inserts(ev, 1), "action": "user_created",
                             "src_ip": None, "result": "success"},
                })
            elif eid == 4688:  # process created (audit policy dependent)
                exe = _inserts(ev, 5)
                cmdline = _inserts(ev, 8)
                name = (exe or "").replace("/", "\\").split("\\")[-1] or None
                events.append({
                    "event_type": "process", "observed_at": observed,
                    "severity_hint": hint_for_process(cmdline or ""),
                    "process": {
                        "pid": None,  # event log carries the new PID only in
                        "ppid": None,  # hex inserts; sent null, not guessed
                        "name": name, "exe": exe or None,
                        "cmdline": [cmdline] if cmdline else [],
                        "user": _inserts(ev, 10),
                        "started_at": observed,
                        "hash_sha256": None,  # not read off disk here
                    },
                })
            elif eid == 4672:  # special privileges assigned (admin logon)
                events.append({
                    "event_type": "auth", "observed_at": observed,
                    "severity_hint": "low",
                    "auth": {"user": _inserts(ev, 1), "action": "privileged_logon",
                             "src_ip": None, "result": "success"},
                })
        state.win_event_record = newest
    finally:
        try:
            if hand is not None:
                w32.CloseEventLog(hand)
        except Exception:
            pass
    return events


_WIN_RUN_KEYS = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run"),
]


def _read_run_key(root_name: str, subkey: str) -> dict[str, str] | None:
    """Return {value_name: str(value_data)} for a Run key; None on any error
    (missing key, access denied on HKLM without admin, non-Windows)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    root = winreg.HKEY_CURRENT_USER if root_name == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    try:
        key = winreg.OpenKey(root, subkey, 0, winreg.KEY_READ)
    except OSError:
        return None
    values: dict[str, str] = {}
    try:
        i = 0
        while True:
            try:
                name, data, _typ = winreg.EnumValue(key, i)
            except OSError:
                break
            values[str(name)] = str(data)
            i += 1
    finally:
        winreg.CloseKey(key)
    return values


def collect_win_persistence(state: CollectorState) -> list[dict]:
    """Poll Registry Run keys for persistence changes.

    Reported as file-type events with the registry value path as file.path —
    documented mapping, not a claim that the registry is a file.
    """
    events: list[dict] = []
    if sys.platform != "win32":
        return events
    current: dict[str, dict[str, str]] = {}
    for root_name, subkey in _WIN_RUN_KEYS:
        vals = _read_run_key(root_name, subkey)
        if vals is not None:
            current[f"{root_name}\\{subkey}"] = vals

    if not state.run_baselined:
        state.run_values = current
        state.run_baselined = True
        return events

    for key_path, vals in current.items():
        old = state.run_values.get(key_path, {})
        for name, data in vals.items():
            if name not in old:
                action = "created"
            elif old[name] != data:
                action = "modified"
            else:
                continue
            events.append({
                "event_type": "file", "observed_at": now_iso(),
                "severity_hint": "high",  # persistence change: high-interest
                "file": {
                    "path": f"{key_path}\\{name}",
                    "action": action,
                    "hash_sha256": hashlib.sha256(data.encode("utf-8",
                                              errors="replace")).hexdigest(),
                    "pid": None, "process_name": None,
                },
            })
        for name in old:
            if name not in vals:
                events.append({
                    "event_type": "file", "observed_at": now_iso(),
                    "severity_hint": "high",
                    "file": {
                        "path": f"{key_path}\\{name}",
                        "action": "deleted",
                        "hash_sha256": None,
                        "pid": None, "process_name": None,
                    },
                })
    state.run_values = current
    return events


# --------------------------------------------------------------------------- #
# Spool + ingest
# --------------------------------------------------------------------------- #

def read_spool(spool_path: Path) -> list[dict]:
    events: list[dict] = []
    if not spool_path.exists():
        return events
    try:
        with open(spool_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # corrupt line: drop it, keep going
    except OSError as exc:
        log.warning("could not read spool %s: %s", spool_path, exc)
    return events


def write_spool(spool_path: Path, events: list[dict]) -> None:
    """Persist unsent events. Never silently drop: a failed send lands here."""
    if not events:
        return
    spool_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(spool_path, "a", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")
        log.info("spooled %d unsent event(s) to %s", len(events), spool_path)
    except OSError as exc:
        log.error("SPOOL WRITE FAILED — %d event(s) LOST: %s", len(events), exc)


def clear_spool(spool_path: Path) -> None:
    try:
        spool_path.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("could not clear spool: %s", exc)


def send_events(cfg: dict, events: list[dict]) -> tuple[bool, dict]:
    """POST a batch to /events/ingest. Returns (ok, response_summary).

    Backend rejections are logged honestly — never silently dropped.
    """
    url = cfg["backend_url"].rstrip("/") + "/api/v1/events/ingest"
    body = {"device_id": cfg["device_id"], "events": events}
    try:
        resp = requests.post(
            url, json=body,
            headers={"X-API-Key": cfg["api_key"]},
            timeout=30)
    except requests.RequestException as exc:
        return False, {"error": f"connection failed: {exc}"}
    try:
        data = resp.json()
    except ValueError:
        data = {}
    summary = {
        "http": resp.status_code,
        "accepted": data.get("accepted"),
        "rejected": data.get("rejected"),
        "errors": data.get("errors", []),
    }
    if resp.status_code >= 400:
        log.error("ingest rejected: HTTP %s: %s", resp.status_code, resp.text[:500])
        return False, summary
    if summary["rejected"]:
        # Backend refused some events — log them loudly, do not resend.
        log.warning("backend rejected %s event(s): %s",
                    summary["rejected"], json.dumps(summary["errors"])[:1000])
    return True, summary


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

def run_cycle(state: CollectorState, cfg: dict, config_path: Path,
              spool_path: Path) -> None:
    # 1. Ensure registration.
    if not cfg.get("device_id"):
        log.info("no device_id — attempting registration…")
        if not register_device(cfg, config_path):
            log.error("not registered; will retry next interval")

    # 2. Collect (runs even when unregistered — events spool, nothing is lost).
    events: list[dict] = []
    events += collect_processes(state)
    events += collect_network(state)
    events += collect_files(state, cfg.get("watch_paths") or default_watch_paths())
    events += collect_auth(state, cfg, config_path)
    if sys.platform == "win32":
        events += collect_win_events(state)
        events += collect_win_persistence(state)
    if events:
        log.info("collected %d event(s)", len(events))

    # 3. Flush: spooled (older) events first, then new ones.
    pending = read_spool(spool_path) + events
    if not pending:
        return
    if not cfg.get("device_id"):
        # Not registered yet: keep old spool + new events, in order.
        clear_spool(spool_path)
        write_spool(spool_path, pending)
        log.info("%d event(s) awaiting registration", len(pending))
        return
    ok, summary = send_events(cfg, pending)
    if ok:
        clear_spool(spool_path)
        log.info("ingest ok: accepted=%s rejected=%s",
                 summary.get("accepted"), summary.get("rejected"))
    else:
        # Rewrite spool as old+new so nothing is lost and nothing duplicates.
        clear_spool(spool_path)
        write_spool(spool_path, pending)
        log.error("ingest failed (%s); %d event(s) spooled",
                  summary.get("error", f"HTTP {summary.get('http')}"), len(pending))


def check_config(cfg: dict) -> bool:
    if not cfg.get("backend_url"):
        print("ERROR: backend_url is not set. Edit the config file and add your "
              "backend URL, e.g. \"backend_url\": \"https://aisoc2-backend.onrender.com\"",
              file=sys.stderr)
        return False
    if not cfg.get("api_key"):
        print("ERROR: api_key is not set. In the EDYSOR product go to Settings → "
              "API Keys, create a key, and paste it into the config file.",
              file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EDYSOR reference endpoint sensor (Linux/macOS/Windows).")
    parser.add_argument("--config", default=str(default_config_path()),
                        help="config file path (default ~/.config/edysor/sensor.json)")
    parser.add_argument("--once", action="store_true",
                        help="run a single collection cycle, then exit")
    parser.add_argument("--register-only", action="store_true",
                        help="register the device and exit")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout)

    config_path = Path(args.config)
    spool_path = default_spool_path(config_path)
    cfg = load_config(config_path)
    if not config_path.exists():
        save_config(config_path, cfg)
        log.info("wrote default config to %s — edit backend_url and api_key",
                 config_path)
    detect_platform()  # exits on unsupported OS
    if not check_config(cfg):
        return 2

    if args.register_only:
        return 0 if register_device(cfg, config_path) else 1

    state = CollectorState()
    interval = int(cfg.get("interval_seconds", DEFAULT_INTERVAL) or DEFAULT_INTERVAL)

    if args.once:
        run_cycle(state, cfg, config_path, spool_path)
        # Second quick pass so --once shows real diffs (new procs/conns/files
        # observed after baselining) — still a single test run.
        time.sleep(2)
        run_cycle(state, cfg, config_path, spool_path)
        return 0

    log.info("sensor starting (interval %ds, spool %s)", interval, spool_path)
    try:
        while True:
            run_cycle(state, cfg, config_path, spool_path)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("stopped by user")
    return 0


if __name__ == "__main__":
    sys.exit(main())
