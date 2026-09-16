#!/usr/bin/env bash
# Verify the golden vectors with the system OpenSSL binary.
#
# This is deliberately a *different* implementation from the Python library that
# produced the vectors. Agreement between the two is what rules out a
# single-library bug; a disagreement is a release blocker, not a warning.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "openssl: $(openssl version)"
fail=0
total=0

for vector in "$HERE"/*/*.json; do
  # Signature vectors only; parse and binding checks are not OpenSSL's job.
  check=$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1])).get('check','signature'))" "$vector")
  [ "$check" = "signature" ] || continue
  sig_b64=$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['signature'])" "$vector")
  [ -n "$sig_b64" ] || { echo "  [skip] $(basename "$vector") (empty signature)"; continue; }

  total=$((total+1))
  "$PY" - "$vector" "$WORK" <<'PYEOF'
import base64, json, sys, pathlib
from cryptography.hazmat.primitives import serialization
from medcrypto.keys import load_public_key
vector = json.load(open(sys.argv[1])); work = pathlib.Path(sys.argv[2])
pub = load_public_key(base64.b64decode(vector["public_key"]))
work.joinpath("pub.der").write_bytes(
    pub.public_bytes(serialization.Encoding.DER,
                     serialization.PublicFormat.SubjectPublicKeyInfo))
work.joinpath("payload.bin").write_bytes(base64.b64decode(vector["payload"]))
work.joinpath("sig.bin").write_bytes(base64.b64decode(vector["signature"]))
work.joinpath("meta").write_text(f"{vector['context']}\n{vector['expected']}\n")
PYEOF

  context=$(sed -n 1p "$WORK/meta")
  expected=$(sed -n 2p "$WORK/meta")
  name=$(basename "$vector" .json)

  if openssl pkeyutl -verify -pubin -inkey "$WORK/pub.der" -keyform DER \
       -rawin -in "$WORK/payload.bin" -sigfile "$WORK/sig.bin" \
       -pkeyopt "context-string:$context" >/dev/null 2>&1; then
    actual=VALID
  else
    actual=INVALID
  fi

  if [ "$actual" = "$expected" ]; then
    echo "  [ok  ] $name ($actual)"
  else
    echo "  [FAIL] $name: openssl says $actual, vector expects $expected"
    fail=$((fail+1))
  fi
done

echo
if [ "$fail" -ne 0 ]; then
  echo "$fail of $total signature vectors DISAGREE with OpenSSL"
  exit 1
fi
echo "all $total signature vectors agree with OpenSSL"
