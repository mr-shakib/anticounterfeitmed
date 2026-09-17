# Documentation Index

Project: **AI-based, post-quantum cryptography-enabled counterfeit medicine identification tools for better treatment outcomes in Bangladesh.**

The authoritative requirements document is [`Medicine_Verification_Implementation_Plan.md`](../Medicine_Verification_Implementation_Plan.md) (the SRS) at the repository root. **The SRS wins any conflict with these documents.** Everything in `docs/` exists to turn that SRS into something buildable; where a doc here proposes a deviation, it is marked **DEVIATION** and carries a rationale.

## Reading order

| # | Document | Read it when |
| --- | --- | --- |
| 01 | [Scope and roles](01-scope-and-roles.md) | Before agreeing to build anything — what is in, out, and deferred |
| 02 | [Architecture](02-architecture.md) | Setting up the repo; understanding service boundaries |
| 03 | [Tech stack](03-tech-stack.md) | Pinning dependencies; justifying a choice |
| 04 | [Domain model](04-domain-model.md) | Writing migrations or touching the lifecycle |
| 05 | [API contract](05-api-contract.md) | Implementing or calling any endpoint |
| 06 | [Cryptography design](06-crypto-design.md) | Anything that signs, verifies, or handles a key |
| 07 | [Security and privacy](07-security-and-privacy.md) | Handling tokens, sessions, logs, or attestation |
| 08 | [Concurrency and failure](08-concurrency-and-failure.md) | Writing the confirm transaction or the outbox |
| 09 | [Consumer app](09-consumer-app.md) | Building Flutter screens or result copy |
| 10 | [Staff portal and landing page](10-staff-portal-and-landing.md) | Building admin/manufacturer screens or the public page |
| 11 | [Testing and acceptance](11-testing-and-acceptance.md) | Before claiming a milestone gate is met |
| 12 | [Environments and DevOps](12-environments-and-devops.md) | Deploying, backing up, or rotating a secret |
| 13 | [Week 0 spikes](13-week-0-spikes.md) | **Start here on day one** |
| 14 | [Roadmap](14-roadmap.md) | Planning the next two weeks |
| 15 | [Open decisions](15-open-decisions.md) | You are blocked on someone else's answer |
| 16 | [Glossary](16-glossary.md) | A term is ambiguous |

## Status

**In development.** Backend foundation, shared crypto library and the golden vectors exist and pass. Run `make check` to reproduce.

| Item | State |
| --- | --- |
| `medcrypto` shared library | Built — canonicalisation, tokens, ML-DSA sign/verify, record builders, binding checks |
| `crypto-vectors/` | 9 golden vectors, passing in Python and cross-checked against the system OpenSSL binary |
| Backend data model | All 9 apps, migrations applied to PostgreSQL 17 |
| Confirm transaction | Built, with fixed lock order and post-lock idempotency recheck |
| Serialization + manufacturing records | Built — token generation, print jobs, ordered step recording, QC rejection voids |
| Signing service (`medsigner`) | Built — isolated package, holds seeds, signs opaque bytes; in-process signing refused outside DEBUG |
| Activation + trust manifest | Built — per-unit signed credentials, honest partial-failure reporting, retry-failures-only, versioned root-signed manifest |
| Prepare (preview) | Built — issues challenges, never redeems |
| Consumer HTTP API | Built — sessions, trust manifest, prepare, confirm, operation status, package status, reports |
| Signed status envelopes | Built — every response signed, nonce-bound, short-lived; negative answers signed too |
| App attestation + rate limits | Built — both credentials mandatory; accept-any attestation refused outside DEBUG |
| Firebase App Check verification | **Built** — offline JWKS verification; rejects wrong issuer/audience/app, expiry, `alg=none` and foreign signatures |
| Receipt outbox worker | **Built** — Celery task, idempotent; a signer failure after commit never undoes a redemption |
| Pilot deployment config | **Built** — Dockerfiles and compose; signer verified internal-only with no DB credentials |
| End-to-end chain | Passing — generate → manufacture → activate → preview → confirm, with app-side signature and binding verification |
| Test suite | 90 tests passing against real PostgreSQL |
| Spike S1 (URL/camera) | **Not started** — needs a real domain and phones (decision D3) |
| Spike S2 (sign/verify) | Server side **done**; Dart side **not started** |
| Spike S3 (one redemption) | **Done** — 100 concurrent attempts yield exactly one first redemption, stable over repeated runs |
| Staff portal, landing, Flutter app | Not started |

### Already verified on this machine (2026-09-16)

These were run as live checks, not assumed. They resolve the largest stack risk in the SRS.

| Question the SRS flagged | Finding | Consequence |
| --- | --- | --- |
| "Confirm Python binding support during the initial spike" (§6.5) | `cryptography` **50.0.1** exposes `hazmat.primitives.asymmetric.mldsa` and `mlkem`, bundling its own OpenSSL 4.0.2 | **The signer can be pure Python.** No CGO, no Go/Rust service, no system-OpenSSL dependency in the image |
| ML-DSA context-string separation (§6.2) | `sign(msg, context=b"...")` / `verify(...)` supported; wrong and empty contexts raise `InvalidSignature` | Domain separation per §6.2 is enforceable by the library, not hand-rolled |
| ML-DSA-65 signature size (§6.1) | Exactly **3,309 bytes**, matching FIPS 204 Table 2 | Signature stays in the API response; the printed QR stays small |
| Key sizes for custody planning (§6.4) | Public key 1,952 bytes; private key seed 32 bytes | A private key is a 32-byte seed — trivially wrappable by a KMS/secret store |
| System OpenSSL | 3.5.5 present, `ML-DSA-44/65/87` listed under `openssl list -signature-algorithms` | Useful as an independent cross-implementation check (see doc 06) |
| JCS canonicalization (§6.2, RFC 8785) | `rfc8785` available on PyPI | No need to hand-write a canonicalizer on the backend |

**Still unverified — this is now the top crypto risk:** ML-DSA *verification inside Flutter/Dart* on real Android ARM64. Flutter is not installed on this machine. See spike S2 in doc 13.
