# Working agreements

Read [docs/00-index.md](docs/00-index.md) first. The authoritative requirements document is `Medicine_Verification_Implementation_Plan.md` at the repo root — **it wins any conflict with `docs/`**.

## Invariants — never violate these without an explicit owner decision

1. **Raw tokens are never persisted or logged.** Store `SHA-256(raw_token)` only. Raw tokens exist solely in the print-generation path and transient request memory. Never in audit events, reports, analytics, error traces, or log lines.
2. **`REDEEMED` is permanent.** Exactly one `FIRST_REDEMPTION` event per unit, enforced by a PostgreSQL partial unique index — not by application logic alone. No API resets a redeemed unit to active.
3. **`GET`/`HEAD`, prefetches, crawlers, and link previews never change package state.**
4. **Consumer endpoints require both a consumer session and a valid App Check token.** A staff session is never a substitute. A header, embedded API key, CORS rule, or user-agent check is not authorization.
5. **The backend never trusts the client's claim that a signature verified.** It re-checks server-side.
6. **Verify signatures on received bytes before parsing or displaying them.** Always with the correct ML-DSA context string.
7. **A valid signature is not sufficient** — also check token commitment, key-to-manufacturer authorization, and credential-to-unit binding.
8. **Never tell a consumer the medicine is genuine or safe.** Only that the code matches the record. The clarification string in [docs/09](docs/09-consumer-app.md) is mandatory on success.
9. **PostgreSQL is the only authority.** Redis is a broker and cache. Never gate a redemption on Redis.
10. **Private keys never touch** the repo, the app, the QR, the JS bundle, or an ordinary database row.

## Scope discipline

**Do not build:** factory/printing/QC interfaces, pharmacy anything, sale events, offline redemption, AI models, iOS, or App Links/Universal Links. These are deferred by the SRS. If a task seems to require one, stop and ask — it usually means the requirement was misread.

## Conventions

- Backend module boundaries in [docs/02](docs/02-architecture.md). Cross-app access goes through service functions, not another app's ORM models.
- Every state transition writes an `AuditEvent` **in the same transaction** as the change.
- Every lock sequence uses the order **organization → batch → unit**. Restriction writers use the same order.
- Consumer-facing result strings are fixed in [docs/09](docs/09-consumer-app.md). **Do not improvise copy** — the wording is a patient-safety requirement.
- Manufacturing completion records always store completion time **and** entry time separately, and are labeled in the UI as manufacturer-asserted.

## Testing

- Test against **real PostgreSQL**. SQLite cannot exercise row locks or partial unique indexes and will give a false pass.
- Any change to `cryptography`, OpenSSL, or the Dart verifier **re-runs `crypto-vectors/`** and is reviewed as a cryptographic change.
- CI fails on: crypto vector mismatch, race-test failure, or any log line matching a 43-character Base64url token.
- Do not claim a milestone gate is met until the corresponding tests in [docs/11](docs/11-testing-and-acceptance.md) pass.

## Honesty requirements

These affect what the project may claim in reports and to users:

- The pilot produces **"PQC-signed verification records"** — not a "fully post-quantum secure system".
- Platform-held manufacturer keys produce a **"platform-managed manufacturer-associated signature"** — not independent proof only the manufacturer could sign.
- Manufacturing records are **manufacturer-asserted**, not captured factory scan evidence.
- **Copying a QR before first redemption remains unsolved.** Say so.
- Repeat scans and rate-limit failures are **not** counterfeit labels.
