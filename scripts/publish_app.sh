#!/usr/bin/env bash
# Build the consumer app and publish it on the hub, in one step.
#
#   make app             build per BUILD_KIND into dist/, and publish nothing
#   make publish-app     build per BUILD_KIND and publish on the hub
#   make play-bundle     build the signed release bundle for Google Play, into
#                        dist/, and publish nothing
#
# Reads infra/.env.deploy (gitignored; see infra/env.deploy.example). What it
# builds is chosen there, by BUILD_KIND:
#
#   pilot (default) -> debug-signed, sends the placeholder attestation token,
#                      which only a backend in accept-any mode takes. Not
#                      distributable beyond the pilot, and said so loudly.
#   release         -> signed with the upload key, attested by Firebase App
#                      Check. Needs all four FIREBASE_* values and
#                      consumer-app/android/key.properties.
#
# Having the Firebase values is not enough reason to switch: Play Integrity
# does not recognise an APK installed from the hub rather than Google Play, and
# a release build refuses to scan without a token. So the switch is explicit.
#
# The root public key is read from the deployed server over SSH, the same way
# provision-keys.sh prints it -- an authenticated channel to our own host, not
# the public API the key exists to verify.
set -euo pipefail

MODE="${1:-hub}"
case "$MODE" in hub|apk|bundle) ;; *) echo "usage: publish_app.sh [hub|apk|bundle]"; exit 1;; esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$ROOT/infra/.env.deploy"
say() { printf "\n\033[36m== %s\033[0m\n" "$1"; }

if [ ! -f "$CONFIG" ]; then
  echo "infra/.env.deploy is missing. Copy infra/env.deploy.example to it and fill it in."
  exit 1
fi
# shellcheck disable=SC1090
. "$CONFIG"

TARGET="${DEPLOY_TARGET:?DEPLOY_TARGET is not set in infra/.env.deploy}"
REMOTE_DIR="${REMOTE_DIR:?REMOTE_DIR is not set in infra/.env.deploy}"
BACKEND_BASE_URL="${BACKEND_BASE_URL:-https://api.pqc.anticounterfeitmed.com}"
COMPOSE="docker compose -f infra/docker-compose.prod.yml -f infra/docker-compose.vps.yml --env-file infra/.env"

say "reading the root public key from $TARGET"
ROOT_PUBLIC_KEY=$(ssh "$TARGET" "cd $REMOTE_DIR && $COMPOSE exec -T api python manage.py shell -c \"
import base64
from apps.trust.models import KeyPurpose, SigningKey
k = SigningKey.objects.filter(purpose=KeyPurpose.ROOT).first()
print(base64.b64encode(bytes(k.public_key)).decode() if k else '')\"" 2>/dev/null | tail -1)
# ML-DSA-65 public keys are 1,952 bytes: 2,604 Base64 characters.
if ! [[ "$ROOT_PUBLIC_KEY" =~ ^[A-Za-z0-9+/]{2600}[A-Za-z0-9+/=]{4}$ ]]; then
  echo "Could not read a root public key from the server. Has provision-keys.sh run?"
  exit 1
fi
echo "  root key: ${#ROOT_PUBLIC_KEY} characters, sha256 $(printf %s "$ROOT_PUBLIC_KEY" | sha256sum | cut -c1-16)…"

DEFINES=(
  --dart-define=BACKEND_BASE_URL="$BACKEND_BASE_URL"
  --dart-define=ROOT_PUBLIC_KEY="$ROOT_PUBLIC_KEY"
)
KIND="${BUILD_KIND:-pilot}"
# Google Play only ever gets the signed, attested release.
[ "$MODE" = bundle ] && KIND=release
if [ "$KIND" = release ]; then
  for name in FIREBASE_PROJECT_ID FIREBASE_APP_ID FIREBASE_API_KEY FIREBASE_MESSAGING_SENDER_ID; do
    [ -n "${!name:-}" ] || { echo "BUILD_KIND=release needs $name in infra/.env.deploy"; exit 1; }
  done
  if [ ! -f "$ROOT/consumer-app/android/key.properties" ]; then
    echo "A release build needs the upload key: see consumer-app/README.md, Release signing."
    exit 1
  fi
  DEFINES+=(
    --dart-define=FIREBASE_PROJECT_ID="$FIREBASE_PROJECT_ID"
    --dart-define=FIREBASE_APP_ID="$FIREBASE_APP_ID"
    --dart-define=FIREBASE_API_KEY="$FIREBASE_API_KEY"
    --dart-define=FIREBASE_MESSAGING_SENDER_ID="$FIREBASE_MESSAGING_SENDER_ID"
  )
  if [ "$MODE" = bundle ]; then
    BUILD=(flutter build appbundle --release)
  else
    BUILD=(flutter build apk --release)
    OUTPUT=app-release.apk
  fi
elif [ "$KIND" = pilot ]; then
  # Profile mode keeps the placeholder attestation token; release mode refuses
  # it. Profile also permits the debug key, so no keystore is needed.
  BUILD=(flutter build apk --profile)
  OUTPUT=app-profile.apk
else
  echo "BUILD_KIND must be pilot or release, not '$KIND'"
  exit 1
fi

say "building the $KIND app against $BACKEND_BASE_URL"
(cd "$ROOT/consumer-app" && "${BUILD[@]}" \
  --target-platform="${APK_PLATFORMS:-android-arm64,android-arm,android-x64}" \
  "${DEFINES[@]}")

if [ "$MODE" = bundle ]; then
  mkdir -p "$ROOT/dist"
  BUNDLE="$ROOT/dist/anticounterfeitmed-consumer.aab"
  cp "$ROOT/consumer-app/build/app/outputs/bundle/release/app-release.aab" "$BUNDLE"
  echo "  $BUNDLE  sha256 $(sha256sum "$BUNDLE" | cut -d' ' -f1)"
  echo "  Upload it in Play Console (Testing > Internal testing). Nothing was published."
  exit 0
fi

if [ "$MODE" = apk ]; then
  mkdir -p "$ROOT/dist"
  APK="$ROOT/dist/anticounterfeitmed-consumer.apk"
  cp "$ROOT/consumer-app/build/app/outputs/flutter-apk/$OUTPUT" "$APK"
  echo "  $APK  ($KIND)  sha256 $(sha256sum "$APK" | cut -d' ' -f1)"
  echo "  Nothing was published."
  exit 0
fi

cp "$ROOT/consumer-app/build/app/outputs/flutter-apk/$OUTPUT" "$ROOT/hub/anticounterfeitmed.apk"
LOCAL_SUM=$(sha256sum "$ROOT/hub/anticounterfeitmed.apk" | cut -d' ' -f1)
echo "  hub/anticounterfeitmed.apk  sha256 $LOCAL_SUM"

say "publishing on the hub"
rsync -az --delete "$ROOT/hub/" "$TARGET:$REMOTE_DIR/hub/"
ssh "$TARGET" "set -e; cd $REMOTE_DIR
  $COMPOSE build hub >/dev/null
  $COMPOSE up -d hub 2>&1 | tail -1"

# Downloaded to a file first: piped straight into sha256sum, a container that is
# still starting yields the digest of nothing and ends the retries early.
LIVE_SUM=$(ssh "$TARGET" "t=\$(mktemp); for i in \$(seq 1 15); do
    curl -sf -o \$t http://127.0.0.1:\${HUB_HOST_PORT:-8080}/app/anticounterfeitmed.apk && break
    sleep 2
  done; sha256sum \$t | cut -d' ' -f1; rm -f \$t")
if [ "$LIVE_SUM" != "$LOCAL_SUM" ]; then
  echo "The hub is serving a different file (sha256 $LIVE_SUM). Not published."
  exit 1
fi
echo "  live download matches"

if [ "$KIND" = pilot ]; then
  cat <<'NOTE'

Published a PILOT build: debug-signed, placeholder attestation. It works only
while the backend runs APP_CHECK_MODE=accept-any. For a signed release, see
BUILD_KIND in infra/env.deploy.example. Switching signing keys means installed
copies must be uninstalled once.
NOTE
fi
