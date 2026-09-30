#!/usr/bin/env bash
# pg_backup.sh — nightly logical backup of the SOC Postgres database.
#
# Reads DATABASE_URL from the environment (same var the app uses).
# Writes:  $BACKUP_DIR/soc-backup-<UTC timestamp>.dump.gz
#          $BACKUP_DIR/manifest.json   (latest backup metadata)
# Keeps the newest $BACKUP_KEEP dumps (default 7), deletes older ones.
#
# Recommended schedule: daily cron / Render cron job. The /api/v1/backup/status
# endpoint reads manifest.json and reports staleness; point BACKUP_MANIFEST_PATH
# at the same file if BACKUP_DIR differs from the app host.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/soc}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
mkdir -p "$BACKUP_DIR"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not set" >&2; exit 1
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="$BACKUP_DIR/soc-backup-${TS}.dump"

echo "[backup] pg_dump -> $DUMP"
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" -f "$DUMP"

gzip -9 "$DUMP"
DUMP_GZ="${DUMP}.gz"
SHA="$(sha256sum "$DUMP_GZ" | cut -d' ' -f1)"
SIZE="$(stat -c%s "$DUMP_GZ")"

python3 - "$BACKUP_DIR/manifest.json" <<EOF
import json, sys
manifest = {
    "last_backup_at": "$TS",
    "file": "$(basename "$DUMP_GZ")",
    "size_bytes": $SIZE,
    "sha256": "$SHA",
    "format": "pg_dump custom + gzip",
}
json.dump(manifest, open(sys.argv[1], "w"), indent=2)
print("[backup] manifest updated:", manifest["last_backup_at"], manifest["size_bytes"], "bytes")
EOF

# Rotation: keep newest $BACKUP_KEEP dumps.
ls -1t "$BACKUP_DIR"/soc-backup-*.dump.gz 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | xargs -r rm -f
echo "[backup] done. kept: $(ls -1 "$BACKUP_DIR"/soc-backup-*.dump.gz 2>/dev/null | wc -l)"
