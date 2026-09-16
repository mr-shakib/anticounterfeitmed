# 12 — Environments and DevOps

Source: SRS §5.1, §10.1.

## Environments

| Environment | Purpose | Data | Keys |
| --- | --- | --- | --- |
| `local` | Developer machines | Seeded synthetic | Throwaway dev keys |
| `staging` | Integration, load tests, store test distribution | Synthetic only | **Separate** dev signing keys + App Check debug config |
| `pilot` | The controlled Android pilot | Real | Production signing keys, real attestation |

**Minimum required by the SRS: one pilot environment plus a separate development/staging environment.** Never share signing keys or App Check configuration between them. **Production must not accept debug attestation tokens.**

## Containers

Services: `api`, `worker`, `beat`, `web`, `landing`, `signer`, `postgres`, `redis`, `proxy`.

Rules:

- `signer` sits on an internal network with **no public route** and **no database or S3 credentials**. Reachable only from `api` and `worker`, over mTLS.
- `postgres` is not publicly exposed.
- The object storage bucket is **private**; access via short-lived pre-signed URLs only.
- Pin base images by digest. Pin Python deps with hashes.

## Secrets

- Signing private keys are **32-byte seeds** — wrap them in a KMS/secret manager and inject at signer start. Never in the repo, never in an env var checked into anything, never in a database row.
- `SigningKey` rows store a **reference only**.
- Rotate App Check and API credentials on staff departure.
- **Verify key recovery before issuance begins.** A signing key you cannot restore means credentials you can never reissue.

## Backups

- PostgreSQL **continuous WAL archiving / PITR** + **encrypted daily backups**.
- **Restore drills are mandatory and are an acceptance test** (doc 11): restore in isolation, confirm redeemed units stay redeemed and signed records still verify.
- **Database recovery must not reopen spent codes.** If acknowledged events are unrecoverable, hold verification for affected units until reconciled — do not treat them as unredeemed.
- Back up signing keys separately, with their own recovery drill.

## CI pipeline

Must run on every change:

1. Lint + type check (`ruff`, `mypy`; `eslint`/`tsc`; `dart analyze`).
2. Backend tests against **real PostgreSQL**.
3. **Golden crypto vectors** — backend, signer, OpenSSL CLI cross-check, and Dart.
4. **Race and retry tests.**
5. **Token-leak scan** — fail on any log fixture or source string matching a 43-char Base64url token pattern.
6. Migration check (no missing migrations; no destructive migration without review).

**A `cryptography` or OpenSSL version bump is reviewed as a cryptographic change and must re-run the vectors.**

## Deployment notes

- TLS 1.3 at the proxy. Hybrid `X25519MLKEM768` is a **next-phase experiment** — when tested, **record the actually negotiated group**; make the experiment fail rather than silently fall back to classical.
- The TLS endpoint terminates protection; **upstream connections need their own**.
- Zero-downtime is not a pilot requirement. Correctness is.

### On hosting

For `staging`, a managed platform (Railway or similar) is reasonable and fast to stand up. For `pilot`, prefer a container host where you control the database, backups, and the signer's network isolation — the signer's isolation and the PITR setup are the two things worth owning. Confirm any managed Postgres offers WAL archiving/PITR before relying on it.

Data residency for Bangladeshi pharmaceutical pilot data may carry regulatory expectations — **confirm with the owner before choosing a region** (doc 15).
