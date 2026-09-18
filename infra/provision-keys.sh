#!/usr/bin/env bash
# Provision signing keys on a deployed instance and publish the first manifest.
#
# Run once, after the first deploy. Running it again is refused rather than
# quietly generating a second set: replacing a key that has already signed
# credentials would leave those credentials unverifiable.
#
# Keys are generated inside the signer's volume. The private seeds never leave
# the server, and nothing here prints one.
set -euo pipefail

TARGET="${1:?usage: provision-keys.sh user@host}"
REMOTE_DIR="${REMOTE_DIR:-/opt/anticounterfeitmed}"
COMPOSE="docker compose -f infra/docker-compose.prod.yml --env-file infra/.env"

ssh "$TARGET" "set -e
  cd $REMOTE_DIR
  existing=\$($COMPOSE exec -T api python manage.py shell -c \"
from apps.trust.models import SigningKey
print(SigningKey.objects.count())\" 2>/dev/null | tail -1)
  if [ \"\$existing\" != \"0\" ]; then
    echo \"This instance already has \$existing signing key(s). Refusing to provision again.\"
    echo 'Replacing a key that has signed credentials would make them unverifiable.'
    exit 1
  fi"

echo "== provisioning root, status and manufacturer keys =="
ssh "$TARGET" "cd $REMOTE_DIR && $COMPOSE exec -T api python manage.py shell -c \"
from apps.organizations.models import Organization, OrganizationType
from apps.trust.models import KeyPurpose
from apps.trust.services import provision_signing_key, publish_trust_manifest

provision_signing_key(purpose=KeyPurpose.ROOT)
provision_signing_key(purpose=KeyPurpose.STATUS)
for org in Organization.objects.filter(type=OrganizationType.MANUFACTURER):
    if not org.signing_keys.filter(purpose=KeyPurpose.ACTIVATION).exists():
        provision_signing_key(purpose=KeyPurpose.ACTIVATION, organization=org)
m = publish_trust_manifest()
print('manifest version', m.version)
\""

echo
echo "== the root public key, to compile into the app =="
echo "   (public half only; the private seed stays on the server)"
ssh "$TARGET" "cd $REMOTE_DIR && $COMPOSE exec -T api python manage.py shell -c \"
import base64
from apps.trust.models import SigningKey, KeyPurpose
k = SigningKey.objects.filter(purpose=KeyPurpose.ROOT).first()
print(base64.b64encode(bytes(k.public_key)).decode())\"" 2>/dev/null | tail -1
