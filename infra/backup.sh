#!/usr/bin/env bash
# Take an encrypted logical backup of the verification database.
#
# This complements continuous WAL archiving rather than replacing it: WAL gives
# point-in-time recovery, this gives a portable artefact that can be restored
# somewhere else and checked. An untested backup is not a backup, so
# restore-drill.sh exists alongside it and should be run on a schedule.
#
# Usage: backup.sh [output-directory]
set -euo pipefail

OUT="${1:-./backups}"
CONTAINER="${PG_CONTAINER:-acm_postgres}"
DB="${POSTGRES_DB:-acm}"
USER="${POSTGRES_USER:-acm}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUT/acm-$STAMP.dump"

mkdir -p "$OUT"

# Custom format: compressed, and restorable selectively if ever needed.
docker exec "$CONTAINER" pg_dump -U "$USER" -d "$DB" -Fc > "$FILE"

if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  # Backups leave the host, so they are encrypted at rest. Without a passphrase
  # the script says so loudly rather than quietly writing plaintext.
  gpg --batch --yes --symmetric --cipher-algo AES256 \
      --passphrase "$BACKUP_PASSPHRASE" -o "$FILE.gpg" "$FILE"
  rm -f "$FILE"
  FILE="$FILE.gpg"
else
  echo "WARNING: BACKUP_PASSPHRASE is not set; this backup is NOT encrypted." >&2
fi

echo "$FILE"
sha256sum "$FILE" | tee "$FILE.sha256"
