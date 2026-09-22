# 07 — Security and Privacy

Source: SRS §2.2, §2.3, §5.2, §7.

## The actual security boundary — read this first

The QR token is **readable by anyone who can see the uncovered QR and has a decoder that exposes raw codewords**. An ordinary scanner shows only the public URL (doc 09, D21); that stops casual reading and re-encoding of the text, not a determined reader, and not a photocopy of the printed symbol. App restriction is enforced by the API. It **cannot** make a copied QR undecodable, and it **cannot** stop someone using the genuine app with a copied token.

**The unresolved attack is copying before first redemption.** Someone who reads the QR at the factory, or after scratching, can put a copy on another package and redeem first. The first response alone cannot tell which physical package is genuine.

What actually addresses it: physical controls, label reconciliation, scratch integrity, supply-chain evidence, and investigation. **ML-DSA does not remove this risk.** Say so in every report.

## Token handling rules

| Rule | Detail |
| --- | --- |
| Generation | 32 cryptographically random bytes → unpadded Base64url (43 chars) |
| Never | An incrementing serial, or a hash of predictable product data |
| Storage | `SHA-256(raw_token)` only, as the DB lookup value |
| Raw token lifetime | Controlled print-generation path + transient request memory. Nothing else. |
| Forbidden locations | Audit events, reports, analytics, support screenshots, error traces, ordinary logs |

### Print artifact handling

- Keep encrypted print artifacts **only until the job is reconciled**, then delete within **24 hours** and record deletion metadata.
- A reprint after reconciliation requires **voiding and replacing** the affected unit.
- **Review printer spool retention.** Hashing the database does not remove copies the factory already holds. This is an operational control, not a software one — raise it with the manufacturer.

## Public landing page (SRS §2.2)

Current labels open the landing page with no token at all: the URL an ordinary scanner reads is just `https://anticounterfeitmed.com/`. Labels printed in the original format put the token in the URL fragment, which keeps it out of HTTP request paths but lets **browser scripts and the scanner** read it — so the rules below still stand for as long as any such label exists.

- Serve the landing page **directly at `/`**. Do not rely on a redirect to strip a token.
- At page startup, remove the fragment with `history.replaceState` **without sending it anywhere**.
- **No analytics, no advertising, no third-party scripts, no URL-capturing error reporting.** This is why `landing/` is a separate static deployable (doc 02).
- Set a restrictive **Content-Security-Policy** and `Referrer-Policy: no-referrer`.
- Show instructions to open the official app and rescan. Store buttons carry **no package token**.
- **Never** call verification or redemption APIs from this page.

Do **not** register the printed URL as an Android App Link or iOS Universal Link in the first version — that would open the app directly and break the required camera→website behavior.

## Official-app enforcement (SRS §2.3)

Consumer API endpoints require **both**:

1. **A server-issued consumer session credential**, stored in the device's protected credential storage. An anonymous installation session is sufficient — **phone-number registration is unnecessary**.
2. **A valid Firebase App Check token** — Play Integrity on Android, App Attest on supported Apple devices. Verified on the Django backend, allowing only the intended mobile app IDs.

Rules:

- Create anonymous sessions **only after** validating app attestation.
- Use random **opaque** session tokens; store **hashes** server-side; support expiry and revocation.
- Reinstallation creates a new identity. It does **not** prove a different person is scanning.
- Attestation failure → "Unable to verify on this device."
- **Production must not silently accept debug tokens.** Separate development credentials; store test distribution for the pilot.
- App Check **reduces** abuse. It does not eliminate it.

Also enforce server-side role checks, rate limits, single-use challenges, and idempotency.

## Repeated scans — deterministic rules first

| Event | Treatment |
| --- | --- |
| Retry with same idempotency key | Same operation; no new scan count |
| User reopens saved receipt | History view; no new event |
| New confirmation on a redeemed unit | Repeat event; show prior-verification warning; flag for assessment |
| Same installation repeats a check | Low priority; identity is only an installation/session signal |
| **Distinct installations confirm the same unit** | **Higher-priority review — still not automatic proof of counterfeiting** |
| Pre-activation check attempt | Limited security telemetry; surface to manufacturer if repeated |
| Invalid/untrusted credential | Decline redemption; open technical/security investigation |
| Unknown-token bursts | Rate-limit and investigate abuse **without changing unrelated units** |

**Rate-limit failures are not counterfeit labels.** Neither is scan repetition. An anomaly model can only be evaluated once investigation outcomes provide real labels (doc 08 of the SRS §8).

## Privacy

- **Do not request location** for ordinary verification.
- **Never** show another consumer's identity or location.
- History is scoped to the installation's own session. A user must not be able to read another session's history (acceptance test, doc 11).
- Concern-report photos are **optional and consented**. A consumer may optionally name a pharmacy; this requires no pharmacy account.
- The database records **a server-side verification event** — not proof that the consumer actually read the returned screen.

## Staff access

- Organization-scoped roles; **MFA required for privileged staff**; revoke on departure.
- Object-level authorization on **every** staff endpoint — not just view-level.
- Admin cannot edit signed data or reset redeemed units. Investigations **add a conclusion**; they never erase history.

## Logging policy

Log request IDs, actor IDs, organization IDs, unit IDs, and outcomes. **Never** log raw tokens, session credentials, App Check tokens, or private key material. Add a CI check / log filter that fails on anything resembling a 43-char Base64url token.
