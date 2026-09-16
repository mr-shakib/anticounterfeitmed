#!/usr/bin/env bash
# Fail if a raw package token appears anywhere it should not.
#
# A token is 43 Base64url characters. Real ones must never reach source, logs or
# fixtures -- only SHA-256 digests are ever persisted. The golden vectors are the
# one legitimate exception: they carry deliberately fixed test tokens.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 43 base64url chars bounded by non-token characters, to cut false positives.
PATTERN='(^|[^A-Za-z0-9_-])[A-Za-z0-9_-]{43}([^A-Za-z0-9_-]|$)'

hits=$(grep -rInE "$PATTERN" \
        --include='*.py' --include='*.dart' --include='*.ts' --include='*.tsx' \
        --include='*.js' --include='*.log' --include='*.json' --include='*.yml' \
        --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.git \
        --exclude-dir=crypto-vectors \
        . 2>/dev/null || true)

if [ -n "$hits" ]; then
  echo "Possible raw token committed:"
  echo "$hits"
  echo
  echo "Tokens must never be stored or committed. Only SHA-256 digests persist."
  exit 1
fi
echo "no raw tokens found outside crypto-vectors/"
