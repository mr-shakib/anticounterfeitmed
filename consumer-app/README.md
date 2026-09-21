# Consumer app

The Android app a patient scans with. It decodes the QR locally, verifies the
platform's ML-DSA signatures before showing anything, and records at most one
first verification per package.

What it tells someone is deliberately narrow: whether a scanned code matches a
manufacturer's signed record. Never that the medicine is genuine or safe. The
result wording is fixed in [docs/09](../docs/09-consumer-app.md) and must not be
improvised — see `lib/l10n/strings.dart`.

## Running it locally

Local setup, including the backend and a seeded token, is in
[docs/17](../docs/17-running-locally.md).

```bash
flutter run --dart-define=ROOT_PUBLIC_KEY="$ROOT"
flutter test
```

Debug and profile builds send a placeholder attestation token, which the
development backend accepts in its `accept-any` mode. Release builds do not —
see below.

## Build-time configuration

Nothing environment-specific is committed. Every value arrives as a
`--dart-define`.

| Define | What it is |
| --- | --- |
| `BACKEND_BASE_URL` | API origin. Defaults to the emulator's host, `http://10.0.2.2:8000` |
| `ROOT_PUBLIC_KEY` | Base64 root public key. Everything else the app trusts is authorised by a manifest this key signs |
| `FIREBASE_PROJECT_ID` | Firebase project supplying App Check |
| `FIREBASE_APP_ID` | Firebase Android app id |
| `FIREBASE_API_KEY` | Firebase API key |
| `FIREBASE_MESSAGING_SENDER_ID` | Firebase sender id (the project number the backend also uses) |
| `APP_CHECK_PROVIDER` | `play-integrity` (default), or `debug` for emulator work. A release build refuses `debug` |

The Firebase values are not secrets — an APK carries them in the clear either
way — but they are environment-specific, so they are passed as defines rather
than committed as `google-services.json`. That also keeps the build working for
anyone who does not have the file.

## Attestation

Every consumer request carries `X-App-Check`. The backend requires it *and* a
session credential, and a staff session is never a substitute.

`lib/data/attestation.dart` fails closed:

- a release build with no Firebase project **refuses to produce a token**;
- a release build may not use the App Check debug provider;
- any failure to obtain a token becomes "Unable to verify on this device", and
  no request is made.

Two things still need doing before a pilot, both from
[docs/15](../docs/15-open-decisions.md):

- **D9** — create the Firebase project and register the Android app, then
  supply the four `FIREBASE_*` defines and set the backend to
  `APP_CHECK_MODE=firebase`.
- **D20** — Play Integrity needs Play Services and, in practice, a
  Play-distributed build. A sideloaded APK will fail attestation, and the
  person is then locked out of checking their medicine entirely. That is a
  product decision, not a technical one, and it is still open. `AttestationRejected`
  in `lib/data/api_client.dart` is the single place a degraded path would go.

## Release signing

Release builds are signed with the upload key. There is no debug-key fallback:
a debug-signed APK can be resigned by anyone and Play will not accept it.

Create the keystore once, outside any repository, and back it up — losing it
means the app can never be updated under the same identity again:

```bash
keytool -genkey -v -keystore ~/keys/anticounterfeitmed-upload.jks \
  -keyalg RSA -keysize 4096 -validity 10000 -alias upload
```

Then copy `android/key.properties.example` to `android/key.properties` and fill
it in. Both the keystore and `key.properties` are gitignored.

Without `key.properties`, a release build stops with instructions rather than
producing something that cannot be distributed. `ALLOW_DEBUG_SIGNING=1` opts
back in for a throwaway local build, and nothing else.

## Building

```bash
make apk        # signed release build into dist/, from the repository root
make apk-dev    # profile build for sideloaded development; not distributable
```

`make apk` requires `BACKEND_BASE_URL`, `ROOT_PUBLIC_KEY` and the four
`FIREBASE_*` values in the environment, and names any that are missing.

## Layout

| Path | What lives there |
| --- | --- |
| `lib/core/` | QR payload parsing, outcome semantics |
| `lib/crypto/` | ML-DSA verification, credential binding, the on-device vector self-check |
| `lib/data/` | API client, attestation, session and receipt storage, trust manifest |
| `lib/screens/` | Scan, package preview, result, history, report |
| `lib/l10n/` | English and Bangla strings. The Bangla is a working draft pending review (D10) |
| `assets/crypto-vectors/` | The same vectors `crypto-vectors/` checks on the server |

`test/` runs on the host; `integration_test/live_flow_test.dart` drives a real
backend from a real device.
