# 13 — Week 0 Spikes (start here)

Source: SRS §9. *"For the first three working days, implement only the URL/camera experiment, the activation-credential sign/verify spike, and a PostgreSQL test proving exactly one redemption under simultaneous requests. These resolve the biggest architectural risks before building dashboards."*

**Write no dashboard, no CRUD screen, and no Django model beyond what these spikes need.** Every one of these can invalidate an architectural assumption. Finding that out in week 1 is cheap; finding it out in week 8 is not.

Spike code lives in `spikes/` and is **throwaway** — except `crypto-vectors/`, which is permanent.

---

## S1 — URL and camera experiment  🟨 MATERIALS READY, PHONE TEST OUTSTANDING

**Risk:** the entire two-experience design (SRS §2) assumes a normal phone camera opens the website and the official app handles the same URL. If real cameras behave differently, the design changes.

**Do:**

1. Stand up a placeholder page at the real domain (or a stand-in host) serving `/` directly.
2. Generate QR codes for `https://<host>/#v=1&t=<43-char-token>`.
3. Scan with **at least 3 representative Android phones** (the models the pilot will actually use), default camera apps **and** a common third-party QR app.
4. Confirm the fragment survives to the page, and that `history.replaceState` strips it.
5. Confirm **no** request carries the fragment to the server (check access logs — the fragment must never appear).

**Gate:** the printed URL opens the correct website on every tested phone; the token never reaches server logs; zero state changes occur from any browser action.

**Progress (2026-09-17).** The domain is owned and already serving a Next.js site at `/` with **no analytics and no third-party scripts** — every script is same-origin, so nothing on the live page can currently read a token. It returns `200` directly at `/` with no redirect, which is what the SRS requires.

Two gaps remain against §2.2, both header-level: there is **no Content-Security-Policy**, and `Referrer-Policy` is `strict-origin-when-cross-origin` rather than `no-referrer`. The page also does not strip the fragment, so a scanned token currently sits in the address bar and browser history.

A compliant replacement page (`landing/`) and its nginx configuration now exist, and `make labels` generates the 80-label print sheet. **What is left is genuinely physical:** print the sheet, scan it with the three pilot phones, and confirm the fragment never appears in server access logs.

**Watch for:** camera apps that pre-fetch or preview the URL; Android Instant Apps / link-handling dialogs interfering; any phone that strips or mangles the fragment. Do **not** register App Links.

---

## S2 — Sign on server, verify on device  ✅ PASSED *(risk retired)*

**Risk:** ML-DSA verification inside Flutter on Android ARM64 is unproven. Everything else in the crypto design depends on it.

**Already resolved — do not redo:**

```text
cryptography 50.0.1 → asymmetric.mldsa (bundles OpenSSL 4.0.2)
ML-DSA-65: sign/verify OK; sig 3309 B; pubkey 1952 B; privkey seed 32 B
context= enforced (wrong/empty context and tampered message → InvalidSignature)
System OpenSSL 3.5.5 produces an identical 3309-byte signature (cross-check)
rfc8785 (JCS) available on PyPI
```

**Do:**

1. Build the canonical activation record (JCS) and sign it server-side with context `medicine-activation-v1`.
2. Commit the result to `crypto-vectors/` — canonical bytes, signature, public key, key id — plus **negative** vectors: tampered byte, wrong context, wrong key, truncated signature, duplicate JSON key, wrong token binding.
3. Verify the vectors in Dart on **a real Android ARM64 device**, evaluating in order:
   - **Dart FFI to a bundled `libcrypto`** (OpenSSL 3.5+; Android ships BoringSSL, so the `.so` must be bundled per ABI — **measure the APK size increase**);
   - a **vetted pure-Dart ML-DSA verifier**, if a credible maintained one exists.
4. Measure verification time on the slowest target phone.
5. Confirm a **matching JCS implementation** in Dart produces byte-identical canonical output.

**Gate (SRS milestone 1):** the same signed bytes verify on server **and** mobile; **every** negative vector fails on both; verification time is acceptable on the slowest phone.

**Result (2026-09-17): PASSED, with the better of the two possible outcomes.**

Pure Dart works. The `pqcrypto` package implements FIPS 204 including the context-string parameter, so option 1 (FFI to a bundled `libcrypto`) was not needed. That removes a whole class of work and risk: no native build, no `.so` per ABI, no APK size penalty, and **ARM64 needs no separate porting effort**, because there is no native code to port.

All 9 golden vectors reach the same verdict in Dart as in Python and under the OpenSSL CLI. Three independent implementations now agree, including context separation, truncated and empty signatures, duplicate JSON keys, and a genuine credential presented against the wrong token.

| Measurement | Value |
| --- | --- |
| Verify, Dart AOT on x86-64 desktop | ~1.9 ms p50 |
| Verify, Flutter release build on Android | **2.5 ms p50** |
| Two signatures per scan (credential + status) | **~5 ms** |
| Release APK | 17 MB, no native crypto bundled |

Five milliseconds is far below perception and irrelevant against the two-second service target. A budget phone an order of magnitude slower stays imperceptible.

Evidence: `docs/evidence/s2-android-selfcheck.png`.

**Still unproven: real ARM64 hardware.** The run used the Pixel 7 emulator, which is **x86_64**, so it demonstrates the Flutter and Android runtime path but not the target ABI or real-device timing. With no native code the ABI risk is low — but low is not measured. Closing it needs one pilot phone over USB, which ties to decision D11. The test to run there is `consumer-app/lib/crypto/self_check.dart`, which reports on the device itself.

**If a future change breaks this**, escalate before proceeding — the options then are a platform-channel native verifier (Kotlin/Swift) or, as a last resort, reduced client-side verification, which weakens the security story and must be an owner decision.

---

## S3 — Exactly one redemption under contention  ✅ PASSED

**Risk:** this is the system's core correctness claim. It must be proven in PostgreSQL, not argued in Python.

**Do:**

1. Minimal schema: `package_unit`, `verification_event`, `verification_operation`.
2. Add the partial unique index:
   ```sql
   CREATE UNIQUE INDEX one_first_redemption_per_unit
       ON verification_event (unit_id)
       WHERE event_type = 'FIRST_REDEMPTION';
   ```
3. Implement confirm with fixed lock order (org → batch → unit), challenge consumption, and idempotency resolution **in one transaction**.
4. Fire **100 concurrent eligible confirmations** at one unit.
5. Fire **100 retries** of a single operation with the same idempotency key.
6. Race a **recall** against a confirmation, both orderings.
7. **Kill the signer after commit**; confirm recovery returns the same event.

**Gate:** exactly one `FIRST_REDEMPTION`; the other 99 classified as repeats; retries inflate nothing; recall ordering behaves per doc 08; post-commit signer failure never rolls back a redemption.

**Result (2026-09-16): PASSED.** Implemented in `apps/verification/services.py`, proven by `backend/tests/test_race_and_idempotency.py`, stable across repeated runs.

One design bug surfaced here and is worth remembering. Resolving idempotency only at the *start* of the transaction is not enough: 100 simultaneous retries all pass that check before any has committed, so the losers then found the challenge already spent and failed a request that had in fact succeeded. The fix is a second idempotency lookup *after* the unit lock is held, which is what the SRS means by resolving an exact retry "before treating the challenge as spent". Any future rework of this transaction must keep both lookups.

**Use real PostgreSQL. SQLite cannot exercise row locks or partial unique indexes** and will give a false pass.

---

## Exit criteria for Week 0

All three gates green, `crypto-vectors/` committed and passing in CI, and doc 15's blocking decisions answered. **Then** start milestone 2 (backend foundation).

If a gate fails, fix the design **before** building on it. That is the entire purpose of spending three days here.
