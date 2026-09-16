#!/usr/bin/env bash
# Fail if a raw package token appears anywhere it should not.
#
# Only SHA-256 digests are ever persisted, so a 43-character Base64url string in
# source, logs or fixtures is a leak. Matching on length alone produces false
# positives -- a Python identifier such as
# "test_trust_manifest_is_signed_and_versioned" is exactly 43 permitted
# characters -- so a candidate must also look like random data: it must contain
# both upper and lower case.
#
# A real token missing either case class has probability around 4e-10, so this
# filter costs essentially no detection while removing identifier noise.
# The golden vectors are the one legitimate exception and are excluded.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PY:-$ROOT/.venv/bin/python}"

grep -rInE '(^|[^A-Za-z0-9_-])[A-Za-z0-9_-]{43}([^A-Za-z0-9_-]|$)' \
      --include='*.py' --include='*.dart' --include='*.ts' --include='*.tsx' \
      --include='*.js' --include='*.log' --include='*.json' --include='*.yml' \
      --include='*.html' --include='*.csv' \
      --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.git \
      --exclude-dir=crypto-vectors --exclude-dir=out \
      . 2>/dev/null | "$PY" "$ROOT/scripts/_filter_token_candidates.py"
