# EDYSOR reference endpoint sensor

A real, working sensor for Linux, macOS, and Windows. Install it on a machine and it
starts sending security telemetry — processes, network connections, file
integrity, auth events — to the EDYSOR backend's event-ingestion API.

## What it does

Every `interval_seconds` (default 30) it:

1. **Processes** — diffs the process table; emits a `process` event per *new*
   process (pid, ppid, name, exe, cmdline, user, start time, SHA-256 of the
   executable best-effort, `null` when unreadable).
2. **Network** — emits a `network` event per *new* outbound TCP/UDP connection
   (pid, process name, src/dst IP/port, proto, direction). Loopback skipped.
   Per-connection byte counters are **not observable** and sent as `null`.
3. **Files** — polls `watch_paths` (default `/etc/crontab`, `/etc/cron.d`,
   `~/.ssh/authorized_keys`) for created/modified/deleted, with best-effort
   SHA-256. The writing process is **unknown** via polling → `null`.
4. **Auth** (Linux only) — tails `/var/log/auth.log` for logins, failed
   logins, sudo. Skipped silently when the log is missing/unreadable.
5. **Windows Event Log** (Windows only, needs `pywin32` + Administrator) —
   reads the Security channel for logons (4624), failed logons (4625),
   process creation (4688, when auditing is enabled), user creation (4720),
   and privileged logons (4672). Event 4688 closes much of the polling gap
   for short-lived processes. Skipped with a logged warning when pywin32 is
   missing or the log can't be opened.
6. **Registry persistence** (Windows only, stdlib `winreg`) — polls the
   `HKCU/HKLM ...\CurrentVersion\Run` keys; added/changed/removed values
   are reported as `file`-type events with the value path as `file.path`.

Events batch-POST to `POST {backend_url}/api/v1/events/ingest` with the API
key in the **`X-API-Key`** header:

```json
{"device_id": "agt-<hex>", "events": [ ... ]}
```

If the backend is unreachable, events append to
`~/.config/edysor/spool.jsonl` and are retried next interval — nothing is
silently dropped, nothing is sent twice. Backend rejections are logged with
their error details.

First run registers automatically via `POST /api/v1/agents/register` and
stores the returned `device_id` in the config.

## Install

```bash
pip install -r requirements.txt            # Linux/macOS: psutil, requests
py -m pip install -r requirements-windows.txt  # Windows: psutil, requests, pywin32
```
Python 3.10+ required on all platforms.

1. In the EDYSOR product: **Settings → API Keys → create a key**.
2. Write `~/.config/edysor/sensor.json`:
   ```json
   {
     "backend_url": "https://aisoc2-backend.onrender.com",
     "api_key": "PASTE-YOUR-KEY-HERE",
     "interval_seconds": 30
   }
   ```
   (`chmod 600` it — it holds a secret. The sensor also does this itself.)
3. Test: `python3 edysor_sensor.py --once`
4. Run persistently: see `edysor-sensor.service` (Linux systemd),
   `nohup python3 edysor_sensor.py &` (macOS), or on Windows PowerShell:
   `Start-Process py -ArgumentList "edysor_sensor.py" -WindowStyle Hidden`.
   On Windows the config lives at `%USERPROFILE%\.config\edysor\sensor.json`,
   and Administrator rights unlock Event Log telemetry.

Flags: `--once` (single cycle, for testing), `--register-only`,
`--config <path>` (use a different config file), `-v` (debug logging).

## `severity_hint`

Each event carries a first-pass `severity_hint` (`info`/`low`/`medium`/`high`).
This is a **small documented heuristic, not a detection verdict** — the exact
rules live in comments in `edysor_sensor.py`:

- file created/modified/deleted under `watch_paths` → `high`
- new process whose cmdline matches `curl|wget|nc|ncat|nmap|base64|xxd|powershell|pwsh|mimikatz`, `/dev/tcp/`, or `base64 -d` → `medium`
- outbound connection to a public IP → `low` (private → `info`)
- failed login → `medium`; login/sudo → `low`

Expect false positives (an admin running `curl` is `medium`). The backend's
ML models do the real scoring.

## LIMITATIONS (honest)

- **User-space polling, not kernel tracing.** Snapshots every interval;
  short-lived processes that start and exit between polls are missed. It is
  not eBPF / ETW / a kernel extension.
- **No DNS capture.** Would need packet capture / root + pcap; deliberately
  not implemented rather than faked.
- **No macOS auth-log parsing.** The unified log needs special entitlements;
  Linux `/var/log/auth.log` is parsed best-effort.
- **File watcher is mtime/size polling, not inotify.** Changes between polls
  coalesce; the writing PID is unknowable → sent as `null`.
- **Unobservable fields are `null`, never invented.** Byte counters, file
  writers, unreadable hashes.
- **Needs root for full visibility** (other users' processes, auth logs). As a
  normal user it still runs but sees less — an honest tradeoff, not a bug.
- **Reference implementation.** A production agent would add: signed
  installers, auto-update, tamper resistance, eBPF/ETW collectors, command
  channel (isolate/kill), and mTLS — all intentionally out of scope here.
