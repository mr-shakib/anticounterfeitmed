# 03 — Tech Stack

Source: SRS §5.1, §6.5. The SRS already fixed most of this; this document pins versions and records the reasoning, including the one choice that live testing changed.

## Pinned stack

| Component | Choice | Notes |
| --- | --- | --- |
| Language (backend) | Python 3.12 | Pinned 2026-09-16. Django 5.2 LTS supports 3.10–3.13; 3.13 is not present on the dev machine and 3.14 would force Django 6.0. Revisit when 3.13 is available. |
| API framework | Django 5.2 LTS + DRF | LTS for a pilot that must be maintained, not the newest release. |
| Database | PostgreSQL 17 | Partial unique indexes, `SELECT … FOR UPDATE`, WAL archiving/PITR. |
| Background jobs | Celery 5.x + Redis | Print generation, bulk activation, receipt outbox. |
| Staff portal | Next.js 15 (App Router) + React | Role-scoped screens. |
| Landing page | Static HTML/CSS, no JS deps | See doc 02 DEVIATION. |
| Consumer app | Flutter (stable, pinned via fvm) | Android first; iOS shares UI but needs its own native verification and attestation work. |
| Object storage | S3-compatible, private bucket | Short-lived print files, reference images, report attachments. |
| **Signing** | **Python + `cryptography` >= 50** | **Changed from the SRS's implied approach — see below.** |
| Canonical JSON | `rfc8785` (PyPI) | RFC 8785 JCS, per SRS §6.2. |
| Attestation | Firebase App Check (Play Integrity / App Attest) | Verified server-side in Django. |
| Reverse proxy | nginx or Caddy, TLS 1.3 | Terminates TLS; hybrid ML-KEM group is a later phase. |

## The signer decision — resolved by testing, not by reading

**SRS §6.5** hedges: *"Confirm Python binding support during the initial spike; if unavailable, keep signing behind the private native service."* It also warns against depending on `liboqs` in production, citing its maintainers' own caution.

I ran the check. Results on this machine (2026-09-16):

```text
cryptography 50.0.1  →  cryptography.hazmat.primitives.asymmetric.mldsa
                        bundles its own OpenSSL 4.0.2
ML-DSA-65 sign/verify .................. OK
signature length ....................... 3309 bytes  (= FIPS 204 Table 2)
public key ............................. 1952 bytes
private key (raw seed) ................. 32 bytes
context=b"medicine-activation-v1" ...... enforced
  wrong context ........................ InvalidSignature
  empty context ........................ InvalidSignature
  tampered message ..................... InvalidSignature
ML-KEM768 / 1024 ....................... also exposed (mlkem)
```

**Therefore: the signing service is plain Python.** Consequences worth stating:

- No CGO, no Rust/Go service, no native build toolchain in the signer image.
- **No dependency on the host's OpenSSL version** — `cryptography`'s wheels bundle their own. This removes an entire class of "works on my machine / breaks in the container" failure that a system-OpenSSL-3.5 approach would have introduced.
- `liboqs` is **not** a production dependency, satisfying the SRS's warning. Keep it, if at all, only for research comparison runs.
- ML-DSA context strings are enforced by the library, so the §6.2 domain separation (`medicine-activation-v1` vs `medicine-status-v1`) is real, not decorative.
- A private key is a **32-byte seed**, so it wraps trivially inside a KMS/secret manager. This makes key custody meaningfully easier than the SRS assumed.

**Caveat to verify before pinning:** confirm `cryptography` 50.x ships wheels for the chosen Python and base image, and pin the exact version with a hash. Treat a `cryptography` major upgrade as a crypto change requiring re-running the golden vectors (doc 06).

**Independent cross-check.** System OpenSSL 3.5.5 lists `ML-DSA-44/65/87` and produced an identical 3,309-byte signature via the CLI. Use it in CI as a second implementation to validate vectors against, guarding against a single-library bug.

## The remaining crypto risk: Dart

Flutter is not installed here, so **ML-DSA verification on Android ARM64 is unproven**. It is now the top technical risk. Spike S2 (doc 13) evaluates, in order of preference:

1. **Dart FFI to a bundled `libcrypto`** from OpenSSL 3.5+. Note Android ships BoringSSL, not OpenSSL — you must **bundle** the `.so` per ABI and accept the APK size cost. iOS needs its own static build.
2. **A pure-Dart ML-DSA verifier**, if a credible maintained one exists. Simpler to ship, but must pass the golden vectors and be constant-time-irrelevant (verification uses only public data, so timing is not a secret-key concern here).

Whichever wins, **the contract is `crypto-vectors/`**, not the library: the same canonical bytes and signature must verify identically on the backend, in the signer, under OpenSSL CLI, and in Dart. Milestone 1's gate is exactly this.

## Deliberately rejected

| Rejected | Why |
| --- | --- |
| Blockchain | Adds no property this needs. PostgreSQL with a unique constraint provides the actual requirement (exactly one first redemption). SRS §5.1 rules it out. |
| Kafka | No event volume justifies it. Celery + an outbox table covers the durability requirement. |
| Service-per-role | SRS §5.1 rules it out. Roles are a permissions concern. |
| `liboqs` in production | Its maintainers explicitly caution against production/sensitive use. Superseded anyway — `cryptography` 50 covers it. |
| Storing signatures in the QR | 3,309 bytes would force a much denser/larger symbol. Signatures travel in the API response. |
| Android App Links / iOS Universal Links | Would open the app directly and break the required camera→website behavior (SRS §2.2). Explicitly deferred. |
| Redis as redemption authority | Not durable. PostgreSQL only. |

## Version pinning policy

- Backend: `uv` or `pip-tools` lockfile with hashes. No unpinned installs.
- Frontend: exact versions, committed lockfile.
- Flutter: `fvm` pinned SDK, committed `pubspec.lock`.
- **Any change to `cryptography`, OpenSSL, or the Dart verifier re-runs the golden vectors in CI and is reviewed as a cryptographic change.**
