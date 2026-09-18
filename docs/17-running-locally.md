# 17 — Running Locally

Every command here was run on a clean checkout before being written down. Where
something is easy to get wrong, the reason is given rather than just the fix.

Five things can run: a database, the backend API, the staff portal, the landing
page, and the consumer app. You rarely need all five at once — pick the section
you need.

## Prerequisites

| Tool | Version used | Needed for |
| --- | --- | --- |
| Python | 3.12 | Backend, signing service, tooling |
| Docker | any recent | PostgreSQL and Redis |
| Node.js | 20+ (24 used here) | Staff portal |
| Flutter | 3.44 stable | Consumer app |
| Android SDK | with an emulator or a device | Running the app |

Only Python and Docker are needed to run the backend and its tests. Node is
needed for the portal, Flutter for the app.

## One-time setup

```bash
git clone https://github.com/mr-shakib/anticounterfeitmed.git
cd anticounterfeitmed

python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r backend/requirements.txt -r requirements-dev.txt

# medcrypto is shared by the backend, the signer and the test suite.
# medsigner is the isolated signing service.
.venv/bin/pip install -e libs/medcrypto -e signer
```

Then start the database and apply migrations:

```bash
make up          # PostgreSQL on 55432, Redis on 56379
make migrate
```

`make up` waits for PostgreSQL to accept connections before returning. Running
migrations or tests against a container that is still starting produces a wall
of connection-refused errors that look like a code fault and are not.

## Running the backend

```bash
make serve       # http://127.0.0.1:8000
```

That is `DJANGO_DEBUG=1 manage.py runserver`. `DEBUG` matters for more than
error pages here: two safety guards are keyed to it, and both refuse to run
outside it.

* `SIGNER_MODE=local` signs inside the web process. Convenient locally, refused
  in a deployment, where `SIGNER_URL` must point at the isolated service.
* `APP_CHECK_MODE=accept-any` performs no app attestation. Also refused outside
  `DEBUG`, so a deployment cannot silently accept development tokens.

Both failures are loud `ImproperlyConfigured` errors naming the cause, rather
than a quiet fallback.

### Seeding something to look at

```bash
make seed        # a manufacturer, a product, a batch, activated units
```

It prints the raw tokens once. They are not recoverable afterwards: the database
stores only `SHA-256(token)`, which is the point.

### An operator account for Django admin

```bash
make operator    # prompts for a username and password
```

Then sign in at <http://127.0.0.1:8000/admin/>. This is a platform-operator tool
only. Django admin has no organization scoping, so anyone who opens it sees
every manufacturer's data — never give it to manufacturer staff. Signed
credentials, verification events and audit records are read-only there by
design.

## Running the staff portal

In a second terminal, with the backend already running:

```bash
cd staff-web
npm install                      # first time only
npm run dev                      # http://localhost:3000
```

The portal proxies `/v1/*` to the backend, so the session cookie is first-party
and there is no CORS to configure. `BACKEND_ORIGIN` overrides the target if the
backend is not on port 8000.

### Signing in

`make seed` creates data but no usable sign-in, so create the demo accounts:

```bash
make staff
```

That makes two accounts, both with the password `devpassword123`, and enrols a
second factor for each:

| Username | Role | Sees |
| --- | --- | --- |
| `demo-admin` | Platform admin | Organizations, investigations, audit, staff access |
| `demo-release-manager` | Release manager | Products, batches, labels, activation, recall |

Signing in takes two steps for both, because each is a privileged role. After
the password, the portal asks for a six-digit code. Without an authenticator app
to hand:

```bash
make staff-code USER=demo-admin
```

Codes rotate every 30 seconds, so fetch one immediately before entering it.

The two accounts deliberately cannot do each other's work: an admin gets 403
from the manufacturer endpoints, and a manufacturer gets 403 from the admin
ones. Admin approves, suspends and investigates; it never acts as a
manufacturer. If you want to see both workspaces, sign in as each in turn.

`make staff` is also the fix if you are locked out: it resets the password and
re-enrols the second factor on an existing account.

Two accounts that look like they should work and do not:

* `operator`, created by `make operator`, is a Django superuser for
  <http://127.0.0.1:8000/admin/>. It has no staff membership, so the portal
  refuses it with `NO_MEMBERSHIP`. The two are separate systems on purpose.
* Any account without an enrolled second factor reaches the password step and
  then nothing, because privileged roles cannot proceed without one.

## Running the landing page

It is a static file with no build step and no dependencies:

```bash
cd landing && python3 -m http.server 4310    # http://127.0.0.1:4310
```

Serving it this way is close enough to check content and the fragment-stripping
behaviour. It does **not** apply the Content-Security-Policy, which nginx sets in
production — see `landing/nginx.conf`.

To see the scanned-code behaviour, open
`http://127.0.0.1:4310/#v=1&t=anything`. The token should vanish from the
address bar immediately, and nothing should be sent anywhere.

## Running the consumer app

The app needs the backend reachable from the device and the root public key
compiled in, because everything it trusts is authorised by a manifest that key
signs.

```bash
# Bind the backend to all interfaces so an emulator can reach it.
DJANGO_DEBUG=1 DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,10.0.2.2 \
  .venv/bin/python backend/manage.py runserver 0.0.0.0:8000
```

Get the root public key the local stack provisioned:

```bash
ROOT=$(DJANGO_DEBUG=1 .venv/bin/python backend/manage.py shell -c "
import base64
from apps.trust.models import SigningKey, KeyPurpose
k = SigningKey.objects.filter(purpose=KeyPurpose.ROOT).first()
print(base64.b64encode(bytes(k.public_key)).decode())" 2>/dev/null | tail -1)
```

Then run it. `10.0.2.2` is how the Android emulator reaches the host; use your
machine's LAN address for a physical phone.

```bash
cd consumer-app
flutter run --release \
  --dart-define=ROOT_PUBLIC_KEY="$ROOT" \
  --dart-define=BACKEND_BASE_URL=http://10.0.2.2:8000
```

To build an installable APK instead:

```bash
make apk         # writes dist/ and prints its sha256
```

Note the defaults: a `make apk` build has no root key or backend URL compiled
in, so it is for checking the interface, not for talking to a server.

### Checking the crypto on a device

```bash
cd consumer-app
flutter test integration_test/live_flow_test.dart -d <device-id> \
  --dart-define=ROOT_PUBLIC_KEY="$ROOT" \
  --dart-define=TEST_TOKEN="<a token from make seed>"
```

This drives the real API: session creation, the signed trust manifest, a
prepared package whose credential is verified and bound to the scanned token,
and a committed confirmation.

## Running the signing service on its own

The backend signs in-process locally, so this is only needed when working on
the service itself or rehearsing the deployed arrangement:

```bash
SIGNER_KEYSTORE_PATH=./.keys SIGNER_AUTH_TOKEN=dev-token \
  .venv/bin/python -m uvicorn medsigner.server:create_app --factory --port 9100
```

Check it with `curl http://127.0.0.1:9100/healthz`. A `POST /sign` without the
bearer token returns 401, which is the point: reaching the port is not the same
as being allowed to sign. It also refuses to start at all without a token.

Port 9100 rather than 9000 because 9000 is widely used by other things and the
bind failure is easy to misread as the service being broken. In the deployed
stack it listens on 9000 inside its own network, where nothing else competes.

Point the backend at it with `SIGNER_MODE=service`, `SIGNER_URL` and
`SIGNER_AUTH_TOKEN`.

## Tests

```bash
make check       # everything CI runs
```

That is four things, and each answers a different question:

| Command | Checks |
| --- | --- |
| `make test` | 151 backend tests against real PostgreSQL |
| `make vectors` | the golden signature vectors in Python |
| `make crosscheck` | the same vectors under the system OpenSSL binary |
| `make leakcheck` | that no raw token is in a tracked file |

The client suites are separate:

```bash
cd consumer-app && flutter test      # 22 tests
cd staff-web && npx tsc --noEmit && npm run lint
```

Tests need PostgreSQL running. They use a real database on purpose: SQLite
cannot exercise row locks or partial unique indexes, so it would report a pass
on exactly the guarantees that matter most.

## Other tasks

| Command | Does |
| --- | --- |
| `make labels` | Generates the 80-label printable QR test sheet |
| `make brand` | Regenerates every sized copy of the project mark |
| `make landing-csp` | Recomputes the landing page's CSP hashes after editing it |
| `make backup` | Takes an encrypted database backup into `./backups` |
| `make restore-drill` | Restores the newest backup in isolation and verifies it |
| `make staff` | Creates or resets the two demo portal accounts |
| `make staff-code USER=...` | Prints a current second-factor code |
| `make down` | Stops PostgreSQL and Redis |

`make restore-drill` is an acceptance test, not maintenance. It confirms that
redeemed units stay redeemed, that the uniqueness index returns with the data,
that a duplicate first redemption is refused afterwards, and that restored
credentials still verify.

## Things that will trip you up

**Connection refused everywhere.** PostgreSQL is not up yet, or stopped. `make
up` waits for readiness; a bare `docker compose up -d` does not.

**Every portal write returns 403 with a CSRF message.** Django checks the
`Origin` header on cookie-authenticated writes. The portal's origin must be in
`CSRF_TRUSTED_ORIGINS`; ports 3000 and 3100 are trusted in `DEBUG`. Behind nginx
the portal and API share an origin and this does not arise.

**The portal shows "Application error: a client-side exception".** A rebuild
happened while `npm run start` was serving the previous build, so the page
references a chunk that no longer exists. Restart the portal. This applies to
deployments too: restart the server after rebuilding, or users get a blank page
until they hard-refresh.

**The app says "Unable to verify on this device".** App attestation failed.
Locally this usually means `APP_CHECK_MODE` is not `accept-any`, or `DEBUG` is
off. This is a hard stop by design — see decision D20, which is still open.

**The app cannot reach the backend.** `runserver 127.0.0.1:8000` is not reachable
from an emulator. Bind to `0.0.0.0` and use `10.0.2.2` as the host.

**The emulator is x86_64.** Useful for the runtime path, but it does not prove
the ARM64 target or real-device timing. One physical phone closes that.

**A signature verifies locally but not on the device, or the reverse.** Run
`make vectors` and `make crosscheck`, then the Flutter tests. All three check the
same files in `crypto-vectors/`; whichever disagrees is the one to look at.
