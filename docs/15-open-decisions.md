# 15 — Open Decisions

Questions the SRS leaves to the project owner. **Blocking** items must be answered before the work they gate begins.

Update the Status column as answers arrive; record the answer and the date.

## Blocking before any serial is generated

| # | Decision | Why it blocks | Status |
| --- | --- | --- | --- |
| D1 | **What is the physical unit?** | **ANSWERED 2026-09-16: one QR per strip. One strip carries exactly one QR. A 1,000-strip run produces 1,000 unique QRs.** Accepted consequence: if a strip is cut and tablets sold separately, the code authenticates only the intact strip, not the separated portions. | **Closed** |
| D2 | **Expiry policy when the label shows only month/year.** | The software **must not guess**. The manufacturer supplies the intended final valid date. Blocks the batch schema. | **Open** |
| D3 | **Domain control for `anticounterfeitmed.com`.** | **ANSWERED 2026-09-17: owned by the project and already serving a public site.** Inspected live the same day: Next.js behind nginx, serves `200` directly at `/` with no redirect, and carries **no analytics or third-party scripts** — every script is same-origin `/_next/static/`. Two §2.2 gaps remain, see D17. | **Closed** |
| D4 | **Which manufacturer partners the pilot?** | Needed for real product/batch data, packaging material, and the physical QR test. Blocks milestone 7. | **Open** |

## Blocking before milestone 4 (activation and trust)

| # | Decision | Why it matters | Status |
| --- | --- | --- | --- |
| D5 | **Key custody model.** Platform-held (pilot default) or manufacturer-operated? | Determines what may honestly be claimed. Platform-held ⇒ must be described as a **platform-managed manufacturer-associated signature**, not independent proof. Manufacturer custody needs their infrastructure. | **Open** |
| D6 | **ML-DSA-44 or ML-DSA-65 for production?** | SRS §6.1 says benchmark before fixing policy. 65 is the starting proposal; 44 has smaller signatures. Decide after the doc 11 comparison. | Open — decide after benchmarks |
| D7 | **Is the reference packaging image authenticated or illustrative?** | If presented as authenticated, its **digest must be in the signed snapshot**. Changes the credential schema. | **Open** |
| D8 | **Which manufacturer identity/registration fields are displayed?** | SRS §6.2: *any displayed* identity/registration field must be added to the signed snapshot. Changes the schema. | **Open** |

## Blocking before milestone 5 (consumer app)

| # | Decision | Why it matters | Status |
| --- | --- | --- | --- |
| D9 | **Google Play Console account and Play Integrity setup.** | Needed for App Check attestation and store test distribution. Long calendar lead time — **start in week 1**. | **Open** |
| D10 | **Bangla translation source.** | Result strings carry clinical-safety meaning. The distinction between "the code matches" and "the medicine is genuine" must survive translation. Needs a native speaker with pharmaceutical context, not machine translation. | **Open** |
| D11 | **Which 3 phone models represent the pilot?** | Fixes the physical QR test matrix and performance targets. Should reflect what patients in the pilot region actually carry, not flagships. | **Open** |

## Non-blocking but decide early

| # | Decision | Notes | Status |
| --- | --- | --- | --- |
| D17 | **What serves `/` once QRs are printed?** | The root currently serves the project's "MedSecure PQC" marketing page, which has no install instructions and no fragment stripping. A scanned QR lands there with the token sitting in the URL bar and browser history. Three options in docs/10. **Needs an owner decision before any QR is printed.** | **Open — blocking print** |
| D18 | **Register a short domain for the QR?** | The printed URL is 2 characters over the QR version-6 boundary, so every label pays for a version-7 symbol (0.377 mm modules at 20 mm / EC Q). A ~10-character host would recover version 6 and an 8% larger module, improving decode margin through the scratch layer. Costs a second domain to own, redirect and protect. Only worth deciding if the 20 mm / Q physical test fails. | Open — revisit after the physical test |
| D19 | **Firebase App Check, Play Integrity direct, or neither?** | Firebase is not a requirement; **attestation** is. Its actual job here is to make session minting expensive, which is what gives per-session rate limits any meaning. Firebase App Check verifies offline against a cached JWKS (no per-request Google call); Play Integrity direct removes the Firebase layer but needs either a server-to-server call per verification or local verdict decryption. The code is already behind `get_attestation_verifier()`, two call sites, so this stays cheap to defer. See D20 for the risk that matters more. | Open |
| D20 | **Does attestation lock out genuine patients?** | Play Integrity and App Check both need Google Play Services and a Play-distributed build. Sideloaded APKs and devices without Play Services are common in Bangladesh. As specified, such a user gets "Unable to verify on this device" and **cannot check their medicine at all**. For a patient-safety tool that is a real harm, and it is a product decision rather than a technical one: hard gate, or degrade to a rate-limited unattested path. **Raise with the owner before the pilot.** | **Open — patient impact** |
| D12 | **Hosting and data residency.** | Bangladeshi pharmaceutical pilot data may carry regulatory expectations. Confirm the region before the pilot environment is built. | Open |
| D13 | **Packaging materials in the pilot.** | The physical QR test repeats per material (720 trials each). More materials, more test time. | Open |
| D14 | **Who staffs the investigation queue?** | The admin investigation features assume a human reviewer exists. Without one, reports accumulate unread. | Open |
| D15 | **Support contact for "Verification is restricted. Contact support."** | That string must point somewhere real before the app ships. | Open |
| D16 | **Retention policy for concern-report photos.** | Consented images of packaging; define retention and deletion. | Open |

## Recorded assumptions (change these only deliberately)

| Assumption | Source |
| --- | --- |
| Android-first; iOS is a later extension | SRS §9, §11 |
| Anonymous installation sessions; **no phone-number registration** | SRS §2.3 |
| Challenge and envelope lifetimes of 120 s | SRS §4.3, pilot starting values |
| Rate limits: 30 prepare/min, 10 confirm/min per session | SRS §7, pilot starting values |
| Trust manifest cache 24 h | SRS §6.4 |
| Label footprints 20 mm and 25 mm, EC levels M and Q | SRS §10.2 |
| Decode gate ≥95% within 3 s | SRS §10.2, project target |
| Service target p95 < 2 s at 20 confirms/s | SRS §10.3, to be measured |
| Signer is pure Python (`cryptography` ≥ 50) | Verified 2026-09-16; doc 03 |
| Landing page is a separate static deployable | **DEVIATION** from SRS §5.1; doc 02 |
