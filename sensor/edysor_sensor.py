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
import shutil
import signal
import socket
import subprocess
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
            # utf-8-sig tolerates the BOM that Windows PowerShell's
            # Set-Content -Encoding utf8 writes; plain utf-8 would choke.
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read config %s (%s); using defaults", path, exc)
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Config holds an API key: restrict permissions.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
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
# Command channel (autonomous response)
#
# The backend's response policy can queue DeviceCommands for THIS device
# (kill a malicious process, block a C2 IP, quarantine a file, remove a
# persistence mechanism). The sensor polls for them, executes via the safe
# handlers below, and acks each one with the result.
#
# Client-side safety mirrors the backend policy:
#   - action allowlist enforced before anything runs;
#   - params must be exact values (no wildcards, no patterns, no paths
#     where a bare name is expected) — anything else is refused;
#   - subprocess is NEVER run with shell=True; argv lists only;
#   - every command runs inside try/except: a bad command is acked as
#     failed, it can never crash the sensor loop.
# --------------------------------------------------------------------------- #

COMMAND_ACTIONS = ("kill_process", "block_ip", "quarantine_file", "remove_persistence")
COMMAND_POLL_SECONDS = 30

_PATTERN_CHARS = ("*", "?", "[", "]")


def _run_argv(argv: list[str]) -> tuple[bool, dict]:
    """Run a fixed argv list (never shell=True). Returns (ok, detail)."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        detail = {
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:2000],
            "stderr": (proc.stderr or "")[:2000],
        }
        return proc.returncode == 0, detail
    except Exception as exc:
        return False, {"error": f"exec failed: {exc}"}


def _refused(reason: str) -> tuple[bool, dict]:
    return False, {"error": f"refused: {reason}"}


def _handle_kill_process(params: dict) -> tuple[bool, dict]:
    pid = params.get("pid")
    name = params.get("name")
    has_pid = isinstance(pid, int) and pid > 0
    has_name = (isinstance(name, str) and name
                and not any(c in name for c in _PATTERN_CHARS)
                and os.path.basename(name) == name
                and "\\" not in name and "/" not in name)
    if not has_pid and not has_name:
        return _refused("need an exact pid (int) and/or exact process name "
                        "(no patterns, no paths)")
    # PID-recycling guard: if both pid and name are given, verify the pid
    # still belongs to that process before killing. A stale pid must never
    # kill an innocent process that reused the number.
    if has_pid and has_name:
        try:
            actual = psutil.Process(pid).name()
            if actual.lower() != name.lower():
                return _refused(
                    f"pid {pid} is now {actual!r}, not {name!r} "
                    f"(pid recycled — kill aborted)")
        except psutil.NoSuchProcess:
            return False, {"error": f"pid {pid} no longer exists"}
        except psutil.AccessDenied:
            return False, {"error": f"cannot inspect pid {pid} (access denied)"}
    if sys.platform == "win32":
        argv = (["taskkill", "/F", "/PID", str(pid)] if has_pid
                else ["taskkill", "/F", "/IM", name])
        ok, detail = _run_argv(argv)
        detail["target"] = params
        return ok, detail
    # POSIX fallback: exact only.
    try:
        if has_pid:
            os.kill(pid, signal.SIGKILL)
            return True, {"target": {"pid": pid}, "method": "SIGKILL"}
        ok, detail = _run_argv(["pkill", "-x", name])  # -x = exact name match
        detail["target"] = {"name": name}
        return ok, detail
    except ProcessLookupError:
        return False, {"error": f"no such pid: {pid}"}
    except PermissionError:
        return False, {"error": f"permission denied killing pid: {pid}"}


def _handle_block_ip(params: dict) -> tuple[bool, dict]:
    ip = str(params.get("ip") or "")
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return _refused(f"not a valid IP: {ip[:64]!r}")
    if not addr.is_global:
        return _refused("only public IPs can be blocked")
    if sys.platform == "win32":
        argv = ["netsh", "advfirewall", "firewall", "add", "rule",
                f"name=EDYSOR-block-{ip}", "dir=out", "action=block",
                f"remoteip={ip}"]
        ok, detail = _run_argv(argv)
        detail["ip"] = ip
        return ok, detail
    if sys.platform.startswith("linux"):
        # iptables OUTPUT rule dropping all traffic to the malicious IP.
        # Needs root / CAP_NET_ADMIN; without it iptables errors and the
        # failure is acked honestly, never faked. Idempotent: an existing
        # rule counts as success. The undo command rides in the ack detail
        # so an operator can lift the block by hand.
        check = ["iptables", "-C", "OUTPUT", "-d", ip, "-j", "DROP"]
        present, _ = _run_argv(check)
        if present:
            return True, {"ip": ip, "already_blocked": True,
                          "rule": f"iptables OUTPUT -d {ip} -j DROP",
                          "undo": f"iptables -D OUTPUT -d {ip} -j DROP"}
        argv = ["iptables", "-A", "OUTPUT", "-d", ip, "-j", "DROP"]
        ok, detail = _run_argv(argv)
        detail["ip"] = ip
        detail["rule"] = f"iptables OUTPUT -d {ip} -j DROP"
        detail["undo"] = f"iptables -D OUTPUT -d {ip} -j DROP"
        return ok, detail
    return False, {"error": f"block_ip is not implemented on {sys.platform} on this build"}


def _handle_quarantine_file(params: dict, config_path: Path) -> tuple[bool, dict]:
    src = params.get("path")
    if not isinstance(src, str) or not src or any(c in src for c in _PATTERN_CHARS):
        return _refused("need an exact file path (no wildcards)")
    p = Path(src)
    try:
        resolved = p.resolve()
    except Exception:
        return _refused(f"cannot resolve path: {src[:200]}")
    if not resolved.is_file():
        return _refused(f"not a file: {src[:200]}")
    # Never quarantine OS binaries — that way lies a bricked machine.
    lowered = str(resolved).lower()
    system_prefixes = (
        os.environ.get("SystemRoot", r"C:\Windows").lower(),
        "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/lib", "/usr/lib",
    )
    if any(lowered.startswith(sp) for sp in system_prefixes):
        return _refused("system directory — quarantine blocked for safety")
    qdir = config_path.parent / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    dest = qdir / f"{resolved.name}.{int(time.time())}.quarantined"
    try:
        shutil.move(str(resolved), str(dest))
    except Exception as exc:
        return False, {"error": f"move failed: {exc}"}
    return True, {"quarantined_to": str(dest), "original": str(resolved)}


def _handle_remove_persistence(params: dict) -> tuple[bool, dict]:
    if sys.platform != "win32":
        return False, {"error": "remove_persistence is Windows-only on this build"}
    task_name = params.get("task_name")
    if isinstance(task_name, str) and task_name \
            and not any(c in task_name for c in _PATTERN_CHARS + ("/", "\\")):
        ok, detail = _run_argv(["schtasks", "/Delete", "/TN", task_name, "/F"])
        detail["task_name"] = task_name
        return ok, detail
    path = params.get("path")
    if not isinstance(path, str) or not path:
        return _refused("need exact 'path' (Run-key value) or 'task_name'")
    # Expected shape: HKCU\Software\Microsoft\Windows\CurrentVersion\Run\<value>
    # or HKLM\... — delete the exact VALUE, never the key.
    try:
        import winreg
    except ImportError:
        return False, {"error": "winreg unavailable"}
    parts = path.split("\\")
    if len(parts) < 3 or parts[0] not in ("HKCU", "HKLM"):
        return _refused(f"path is not a Run-key value: {path[:200]}")
    if "currentversion\\run" not in path.lower():
        return _refused("only Run/RunOnce persistence values may be removed")
    value = parts[-1]
    if not value or any(c in value for c in _PATTERN_CHARS):
        return _refused("need an exact value name (no wildcards)")
    root = winreg.HKEY_CURRENT_USER if parts[0] == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    subkey = "\\".join(parts[1:-1])
    try:
        key = winreg.OpenKey(root, subkey, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, value)
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return False, {"error": f"value already absent: {path[:200]}"}
    except PermissionError:
        return False, {"error": "permission denied (run sensor elevated)"}
    except OSError as exc:
        return False, {"error": f"registry delete failed: {exc}"}
    return True, {"removed": path}


def _ack_command(cfg: dict, cmd_id: int, ok: bool, result: dict) -> None:
    url = (cfg["backend_url"].rstrip("/")
           + f"/api/v1/agents/commands/{cmd_id}/ack")
    try:
        resp = requests.post(
            url,
            json={"status": "acked" if ok else "failed", "result": result},
            headers={"X-API-Key": cfg["api_key"]},
            timeout=30,
        )
        if resp.status_code >= 400:
            log.warning("ack rejected for command %s: HTTP %s", cmd_id,
                        resp.status_code)
    except requests.RequestException as exc:
        log.warning("ack failed for command %s: %s", cmd_id, exc)


def _execute_command(cfg: dict, config_path: Path, cmd: dict) -> None:
    """Execute one command and ack it. Never raises."""
    cmd_id = cmd.get("id")
    action = cmd.get("action")
    params = cmd.get("params") or {}
    log.info("executing command %s: %s %s", cmd_id, action, params)
    try:
        if action not in COMMAND_ACTIONS:
            _ack_command(cfg, cmd_id, False,
                         {"error": f"refused: unknown action {action!r}"})
            return
        if action == "kill_process":
            ok, detail = _handle_kill_process(params)
        elif action == "block_ip":
            ok, detail = _handle_block_ip(params)
        elif action == "quarantine_file":
            ok, detail = _handle_quarantine_file(params, config_path)
        else:  # remove_persistence
            ok, detail = _handle_remove_persistence(params)
        detail["action"] = action
        _ack_command(cfg, cmd_id, ok, detail)
        log.info("command %s %s: %s", cmd_id, "ok" if ok else "FAILED", action)
    except Exception as exc:  # a bad command never kills the sensor
        log.exception("command %s crashed during execution", cmd_id)
        try:
            _ack_command(cfg, cmd_id, False, {"error": f"handler crashed: {exc}"})
        except Exception:
            pass


def poll_commands(cfg: dict, config_path: Path) -> int | None:
    """Fetch pending commands for this device and execute them. Never raises.

    Returns the backend's configured poll_interval_s when the server sends
    a sane value, else None (caller keeps its current cadence).
    """
    device_id = cfg.get("device_id")
    if not device_id:
        return None
    url = (cfg["backend_url"].rstrip("/")
           + f"/api/v1/agents/{device_id}/commands")
    try:
        resp = requests.get(
            url, headers={"X-API-Key": cfg["api_key"]}, timeout=30)
    except requests.RequestException as exc:
        log.warning("command poll failed: %s", exc)
        return
    if resp.status_code == 404:
        log.warning("command poll: agent not found on backend")
        return
    if resp.status_code >= 400:
        log.warning("command poll rejected: HTTP %s", resp.status_code)
        return
    try:
        data = resp.json()
    except ValueError:
        log.warning("command poll: invalid JSON response")
        return
    commands = data.get("commands") or []
    if commands:
        log.info("received %d command(s)", len(commands))
    for cmd in commands:
        _execute_command(cfg, config_path, cmd)
    # Adopt the tenant's configured command-poll cadence when sane.
    try:
        interval_s = int(data.get("poll_interval_s") or 0)
    except (TypeError, ValueError):
        interval_s = 0
    if 10 <= interval_s <= 600:
        return interval_s
    return None


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
    parser.add_argument("--log-file", default=None,
                        help="also write logs to this file (needed for headless/service runs)")
    args = parser.parse_args()

    handlers: list[logging.Handler] = []
    if sys.stdout is not None:  # None under pythonw.exe (no console)
        handlers.append(logging.StreamHandler(sys.stdout))
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    if not handlers:  # last resort: never run silent
        handlers.append(logging.FileHandler("sensor.log", encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True)

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
    last_cmd_poll = 0.0
    cmd_poll_seconds = COMMAND_POLL_SECONDS  # adopted from backend when it sends one
    try:
        while True:
            run_cycle(state, cfg, config_path, spool_path)
            # Command channel: poll for response actions on the tenant's
            # configured cadence (backend sends poll_interval_s).
            # Wrapped so a poll failure never stops collection.
            now_mono = time.monotonic()
            if now_mono - last_cmd_poll >= cmd_poll_seconds:
                last_cmd_poll = now_mono
                try:
                    server_interval = poll_commands(cfg, config_path)
                    if server_interval:
                        cmd_poll_seconds = server_interval
                except Exception:
                    log.exception("command poll crashed (sensor survives)")
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("stopped by user")
    return 0


if __name__ == "__main__":
    sys.exit(main())
