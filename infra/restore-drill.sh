#!/usr/bin/env bash
# Restore a backup into an isolated database and check what must survive.
#
# This is an acceptance test from docs/11, not a maintenance convenience. Its
# purpose is to answer one question: after a restore, is a spent code still
# spent? A recovery that silently reopened redeemed units would hand attackers
# every unit issued before the backup.
#
# It restores into a throwaway container on its own port, never touching the
# running database, and tears it down afterwards.
#
# Usage: restore-drill.sh <backup-file>
set -euo pipefail

BACKUP="${1:?usage: restore-drill.sh <backup-file>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
SRC_CONTAINER="${PG_CONTAINER:-acm_postgres}"
DRILL="acm_restore_drill"
PORT="${DRILL_PORT:-55433}"

cleanup() { docker rm -f "$DRILL" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== recording the state that must survive =="
BEFORE=$(docker exec "$SRC_CONTAINER" psql -U acm -d acm -tA -c "
  select
    (select count(*) from package_unit where lifecycle='REDEEMED'),
    (select count(*) from verification_event where event_type='FIRST_REDEMPTION'),
    (select count(*) from activation_credential);")
echo "  source: redeemed/first-redemptions/credentials = $BEFORE"

echo "== starting an isolated database =="
docker run -d --name "$DRILL" \
  -e POSTGRES_USER=acm -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=acm \
  -p "$PORT:5432" postgres:17-alpine >/dev/null
until docker exec "$DRILL" pg_isready -U acm -d acm >/dev/null 2>&1; do sleep 1; done

echo "== restoring =="
if [[ "$BACKUP" == *.gpg ]]; then
  gpg --batch --quiet --decrypt --passphrase "${BACKUP_PASSPHRASE:?needed for an encrypted backup}" \
      "$BACKUP" | docker exec -i "$DRILL" pg_restore -U acm -d acm --no-owner
else
  docker exec -i "$DRILL" pg_restore -U acm -d acm --no-owner < "$BACKUP"
fi

echo "== checking what survived =="
AFTER=$(docker exec "$DRILL" psql -U acm -d acm -tA -c "
  select
    (select count(*) from package_unit where lifecycle='REDEEMED'),
    (select count(*) from verification_event where event_type='FIRST_REDEMPTION'),
    (select count(*) from activation_credential);")
echo "  restored: redeemed/first-redemptions/credentials = $AFTER"

if [ "$BEFORE" != "$AFTER" ]; then
  echo "FAIL: the restored database does not match the source." >&2
  exit 1
fi

echo "== confirming the uniqueness constraint came back with the data =="
INDEX=$(docker exec "$DRILL" psql -U acm -d acm -tA -c "
  select count(*) from pg_indexes
  where indexname = 'one_first_redemption_per_unit';")
if [ "$INDEX" != "1" ]; then
  echo "FAIL: the first-redemption index is missing after restore." >&2
  exit 1
fi

echo "== confirming a spent code cannot be redeemed again =="
# Insert a duplicate first redemption directly. The database must refuse it.
UNIT=$(docker exec "$DRILL" psql -U acm -d acm -tA -c "
  select unit_id from verification_event where event_type='FIRST_REDEMPTION' limit 1;")
if [ -n "$UNIT" ]; then
  if docker exec "$DRILL" psql -U acm -d acm -q -c "
      insert into verification_event (id, unit_id, event_type, server_time, detail)
      values (gen_random_uuid(), '$UNIT', 'FIRST_REDEMPTION', now(), '{}');" 2>/dev/null; then
    echo "FAIL: a second first-redemption was accepted after restore." >&2
    exit 1
  fi
  echo "  a duplicate first redemption was refused, as it must be"
else
  echo "  no redeemed units in this backup; skipping the duplicate check"
fi

echo "== verifying restored signatures still check out =="
PGPASSWORD=drill "$PY" "$ROOT/scripts/verify_restored_credentials.py" \
  --host 127.0.0.1 --port "$PORT" --db acm --user acm

echo
echo "RESTORE DRILL PASSED"
