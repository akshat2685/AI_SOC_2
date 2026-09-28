"""Backup status endpoint.

Reports the metadata written by backend/scripts/pg_backup.sh (manifest.json).
Honest by construction: if no manifest exists, it says "never" instead of
inventing a backup. `stale` is True when the last backup is older than 25h.

Deploy note: set BACKUP_MANIFEST_PATH to the same manifest file the backup
job writes. On Render, run pg_backup.sh as a scheduled Cron Job with a
persistent disk, or ship the manifest path accordingly.
"""
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import require_roles_dual
from app.domain.models import RoleEnum

router = APIRouter()

ADMIN_ROLES = [RoleEnum.TENANT_ADMIN]
BACKUP_STALE_AFTER_S = 25 * 3600


@router.get("/backup/status")
async def backup_status(_auth=Depends(require_roles_dual(ADMIN_ROLES))):
    manifest_path = os.environ.get(
        "BACKUP_MANIFEST_PATH", "/var/backups/soc/manifest.json"
    )
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "last_backup_at": None,
            "status": "never",
            "stale": True,
            "detail": "no backup manifest found — no successful backup has been recorded",
        }
    ts = manifest.get("last_backup_at")
    stale = True
    try:
        backed_up = datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        stale = (datetime.now(timezone.utc) - backed_up).total_seconds() > BACKUP_STALE_AFTER_S
    except (TypeError, ValueError):
        ts = None
    return {
        "last_backup_at": ts,
        "file": manifest.get("file"),
        "size_bytes": manifest.get("size_bytes"),
        "sha256": manifest.get("sha256"),
        "format": manifest.get("format"),
        "status": "stale" if stale else "ok",
        "stale": stale,
    }
