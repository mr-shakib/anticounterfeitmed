#!/usr/bin/env bash
# Stop local development servers started by `make serve` and the portal.
#
# `pkill -f` is unsafe here: the pattern appears in this script's own command
# line and in the make recipe that calls it, so a naive pkill kills the caller
# before it kills anything else. Matches are collected first and the current
# process tree is excluded.
set -uo pipefail

PATTERNS=(
  "manage.py runserver"
  "next-server"
  "next dev"
  "uvicorn medsigner"
)

# Everything from this script up to the shell that launched make.
self=$$
ancestors=()
pid=$self
while [ "$pid" -gt 1 ]; do
  ancestors+=("$pid")
  pid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
  [ -z "$pid" ] && break
done

is_ancestor() {
  local candidate=$1
  for a in "${ancestors[@]}"; do
    [ "$candidate" = "$a" ] && return 0
  done
  return 1
}

stopped=0
for pattern in "${PATTERNS[@]}"; do
  while read -r target; do
    [ -z "$target" ] && continue
    is_ancestor "$target" && continue
    if kill "$target" 2>/dev/null; then
      echo "  stopped pid $target ($pattern)"
      stopped=$((stopped + 1))
    fi
  done < <(pgrep -f "$pattern" 2>/dev/null)
done

if [ "$stopped" -eq 0 ]; then
  echo "  no dev servers were running"
fi
