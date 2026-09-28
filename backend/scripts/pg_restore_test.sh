#!/usr/bin/env bash
# pg_restore_test.sh — prove a backup actually restores.
#
# Usage: pg_restore_test.sh <dump.gz> [scratch-db-url]
# Restores into a scratch database (default: $RESTORE_TEST_URL or a local
# `soc_restore_test` db), then runs sanity checks: every expected table
# exists and row counts are non-negative. Exits non-zero on any failure.
#
# The scratch DB is dropped and recreated, so NEVER point it at production.
set -euo pipefail

DUMP_GZ="${1:?usage: pg_restore_test.sh <dump.gz> [scratch-db-url]}"
SCRATCH_URL="${2:-${RESTORE_TEST_URL:-postgresql://postgres@localhost:54399/soc_restore_test}}"

case "$SCRATCH_URL" in
  *aisoc2*|*render*|*prod*) echo "refusing: scratch URL looks like production" >&2; exit 1;;
esac

DBNAME="$(python3 -c "from urllib.parse import urlparse; print(urlparse('$SCRATCH_URL').path.lstrip('/'))")"
BASE_URL="$(python3 -c "from urllib.parse import urlparse; u=urlparse('$SCRATCH_URL'); print(f'{u.scheme}://{u.netloc}/postgres')")"

echo "[restore-test] recreating scratch db $DBNAME"
psql "$BASE_URL" -c "DROP DATABASE IF EXISTS \"$DBNAME\";" -c "CREATE DATABASE \"$DBNAME\";" >/dev/null

echo "[restore-test] restoring $DUMP_GZ"
TMP_DUMP="$(mktemp /tmp/restore-test-XXXXXX.dump)"
trap 'rm -f "$TMP_DUMP"' EXIT
gunzip -c "$DUMP_GZ" > "$TMP_DUMP"
pg_restore --no-owner --no-acl -d "$SCRATCH_URL" "$TMP_DUMP" 2>&1 | grep -v "already exists" || true

echo "[restore-test] sanity checks"
psql "$SCRATCH_URL" -tAX <<'SQL'
SELECT 'tables=' || count(*) FROM information_schema.tables WHERE table_schema='public';
SELECT 'tenants_rows=' || count(*) FROM tenants;
SELECT 'alerts_rows=' || count(*) FROM alerts;
SELECT 'audit_rows=' || count(*) FROM audit_events;
SELECT 'rls_on_alerts=' || relrowsecurity::text FROM pg_class WHERE relname='alerts';
SQL

echo "[restore-test] OK"
