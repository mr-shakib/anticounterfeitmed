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

**One exception, by owner decision (2026-09-21): the print-line scan.** `POST /v1/staff/print-scans` reads a printed code back and records `PRINTED` as observed evidence. It is the only staff endpoint that accepts a raw token, and it stays narrow: own organization only, rate-limited, refused once a unit leaves `CREATED`, and it never touches redemption. The rest of the factory/QC end remains deferred.

**Owner decision (2026-09-22, D21): an ordinary scanner sees only the public URL.** This overrides SRS §2.1. The label symbol carries `https://anticounterfeitmed.com/` as its only text, and the token after the terminator, where only raw-codeword readers (ZXing in both the app and the portal camera; ML Kit's `rawBytes` stops at the text, measured 2026-09-22) find it. The layout lives in `libs/medcrypto/medcrypto/labels.py`, and the Python, Dart and TypeScript parsers must all agree on `crypto-vectors/label/`. Do not put the token back in the URL.

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
- Manufacturing records are **manufacturer-asserted**, except the `PRINTED` step where a print-line scan recorded it — that one is observed evidence, and the two are distinguished by `is_manufacturer_asserted` and shown apart in the portal. **QC pass and coating are always assertions**: the coating is applied after scanning and covers the code, so no scan can evidence it.
- **Copying a QR before first redemption remains unsolved.** Say so.
- The hidden label token is **hidden from ordinary scanners, not secret.** A raw-codeword decoder reads it, and a photocopy still scans.
- Repeat scans and rate-limit failures are **not** counterfeit labels.
