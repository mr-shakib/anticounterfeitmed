#!/usr/bin/env bash
# Fail if a raw package token appears anywhere it should not.
#
# Scans the files git actually tracks, which is exactly what "never committed"
# means, and keeps build output and virtualenvs out of scope for free.
#
# Only SHA-256 digests are ever persisted, so a 43-character Base64url string in
# tracked source is a leak. Matching on length alone produces false positives --
# a Python identifier such as "test_trust_manifest_is_signed_and_versioned" is
# exactly 43 permitted characters -- so a candidate must also look like random
# data: it must contain both upper and lower case. A real token missing either
# case class has probability around 4e-10.
#
# Two kinds of tracked file are excluded because they cannot carry a token and
# are full of base64 that trips the filter: the golden vectors, wherever they
# appear -- they are also copied into the Flutter app's assets -- which hold
# deliberately fixed test tokens, and dependency lockfiles, whose integrity
# hashes are base64 digests of published packages.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PY:-$ROOT/.venv/bin/python}"

FILES=$(git ls-files \
          '*.py' '*.dart' '*.ts' '*.tsx' '*.js' '*.jsx' \
          '*.log' '*.json' '*.yml' '*.yaml' '*.html' '*.csv' \
        | grep -vE '(^|/)crypto-vectors/' \
        | grep -vE '(^|/)(package-lock\.json|pubspec\.lock|[^/]*\.lock)$' \
        || true)

# Untracked-but-staged files count too: they are about to be committed.
if [ -z "$FILES" ]; then
  echo "no tracked files to scan"
  exit 0
fi

# shellcheck disable=SC2086
grep -InE '(^|[^A-Za-z0-9_-])[A-Za-z0-9_-]{43}([^A-Za-z0-9_-]|$)' $FILES 2>/dev/null \
  | "$PY" "$ROOT/scripts/_filter_token_candidates.py"
