#!/usr/bin/env bash
# Deploy the verification stack to a VPS.
#
# What this deliberately does NOT do: touch whatever already serves the site at
# the domain root. The API is published on its own subdomain, so an existing
# marketing site keeps working and decision D17 -- what serves "/" once QR codes
# are printed -- stays open rather than being settled by a deployment script.
#
# Idempotent: safe to run again to ship a change.
#
# Usage:
#   ./infra/deploy.sh user@host [api.anticounterfeitmed.com]
set -euo pipefail

TARGET="${1:?usage: deploy.sh user@host [api-domain]}"
API_DOMAIN="${2:-api.pqc.anticounterfeitmed.com}"
REMOTE_DIR="${REMOTE_DIR:-/opt/anticounterfeitmed}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

say() { printf "\n\033[36m== %s\033[0m\n" "$1"; }

say "checking the target"
ssh "$TARGET" 'set -e
  command -v docker >/dev/null || { echo "docker is not installed"; exit 1; }
  docker compose version >/dev/null || { echo "docker compose plugin missing"; exit 1; }
  echo "  docker: $(docker --version)"
  echo "  host:   $(hostname)"'

say "copying the project"
# Source only. Secrets, build output and local state stay on this machine.
rsync -az --delete \
  --exclude ".git" --exclude ".venv" --exclude "node_modules" \
  --exclude ".next" --exclude "build" --exclude ".dart_tool" \
  --exclude "dist" --exclude "backups" --exclude ".keys" \
  --exclude "infra/.env" \
  "$ROOT/" "$TARGET:$REMOTE_DIR/"

say "checking the environment file"
ssh "$TARGET" "set -e
  cd $REMOTE_DIR
  if [ ! -f infra/.env ]; then
    echo 'infra/.env is missing on the server.'
    echo 'Copy infra/.env.example to infra/.env there and fill it in, then rerun.'
    echo 'It is never copied from a developer machine, so secrets stay put.'
    exit 1
  fi
  for required in DJANGO_SECRET_KEY POSTGRES_PASSWORD SIGNER_AUTH_TOKEN; do
    grep -qE \"^\$required=.+\" infra/.env || { echo \"\$required is not set in infra/.env\"; exit 1; }
  done
  echo '  infra/.env present, required values set'"

say "building and starting"
ssh "$TARGET" "set -e
  cd $REMOTE_DIR
  docker compose -f infra/docker-compose.prod.yml --env-file infra/.env build
  docker compose -f infra/docker-compose.prod.yml --env-file infra/.env up -d
  echo '  waiting for the database'
  until docker compose -f infra/docker-compose.prod.yml --env-file infra/.env \
        exec -T postgres pg_isready -U acm -d acm >/dev/null 2>&1; do sleep 2; done"

say "migrating"
ssh "$TARGET" "cd $REMOTE_DIR && docker compose -f infra/docker-compose.prod.yml \
  --env-file infra/.env exec -T api python manage.py migrate --noinput"

say "status"
ssh "$TARGET" "cd $REMOTE_DIR && docker compose -f infra/docker-compose.prod.yml \
  --env-file infra/.env ps"

cat <<NOTE

Deployed to $TARGET.

Still to do by hand, once only:
  1. Point $API_DOMAIN at this host with a DNS A record.
  2. Issue a certificate for it, for example:
       ssh $TARGET 'certbot certonly --webroot -w /var/www/certbot -d $API_DOMAIN'
  3. Provision signing keys and publish the first trust manifest:
       ./infra/provision-keys.sh $TARGET

The site at the domain root is untouched.
NOTE
