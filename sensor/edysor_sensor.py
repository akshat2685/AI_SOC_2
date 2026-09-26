#!/usr/bin/env python3
"""EDYSOR reference endpoint sensor — Linux/macOS, user-space.

Collects process, network, file-integrity and auth events on the local machine
and ships them to the EDYSOR backend event-ingestion API:

    POST {backend_url}/api/v1/events/ingest
    X-API-Key: <api_key>
    {"device_id": "agt-<hex>", "events": [ ... ]}

First run registers the device automatically:
    POST {backend_url}/api/v1/agents/register
    {"hostname", "platform": "linux|macos", "os_version", "arch",
     "agent_version": "0.1.0"}
and stores the returned device_id in the config file.

Honesty notes (read before trusting its output):
  * This is a USER-SPACE, POLLING sensor. It sees a snapshot every
    `interval_seconds`; short-lived processes that start and exit between two
    polls are MISSED. It is not a kernel hook / eBPF tracer.
  * Fields it cannot observe are sent as JSON null, never invented.
    (e.g. per-connection byte counters, the PID that wrote a file.)
  * `severity_hint` is a small documented HEURISTIC, not a detection verdict.
  * DNS capture is intentionally NOT implemented (needs pcap/root).
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
DEFAULT_WATCH_PATHS = ["/etc/crontab", "/etc/cron.d", "~/.ssh/authorized_keys"]
SPOOL_NAME = "spool.jsonl"
CONFIG_NAME = "sensor.json"
HASH_CHUNK = 65536

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
        "watch_paths": list(DEFAULT_WATCH_PATHS),
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
    print(f"ERROR: unsupported platform '{sys.platform}' (linux and macos only)",
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
    events += collect_files(state, cfg.get("watch_paths", DEFAULT_WATCH_PATHS))
    events += collect_auth(state, cfg, config_path)
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
        description="EDYSOR reference endpoint sensor (Linux/macOS).")
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
