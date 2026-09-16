# 09 — Consumer App (Flutter)

Source: SRS §3.4, §4.3. Android first; iOS shares UI code but needs its own native verification, attestation, and device testing.

## Screens

| Screen | Necessary content |
| --- | --- |
| Scan | Camera, torch, framing guidance, **Bangla/English switch**, concise scratch-and-scan instructions |
| Package preview | Brand, generic, strength, dosage form, pack description, manufacturer, batch, manufacturing/expiry dates, reference image, current status |
| Verify action | "Verify this package" — explains that this **records a check and does not record a sale** |
| Result | Outcome, checked time, whether a first verification was recorded, report/help action |
| History | This installation's own receipts, **explicitly labeled with their original check times**; refresh current status online |
| Report concern | Reason, optional packaging photo, optional pharmacy reference/contact, case number, progress |

## URL parsing — strict, local, and first

Before any network call, the app decodes the scanned URL locally and accepts **only**:

- scheme `https`;
- the **exact expected host**;
- the expected fragment version (`v=1`);
- a valid 32-byte (43-char Base64url) token.

**It never opens an arbitrary scanned URL automatically.** Anything failing these checks is treated as "not one of our codes" — not opened, not sent to the API.

Expected format:

```text
https://anticounterfeitmed.com/#v=1&t=<43-character-base64url-token>
```

## Verification sequence

`prepare` → verify signatures locally → display → user taps → `confirm` → verify result → store receipt. Full sequence in doc 05.

The app verifies, **before showing any package information**: the trusted key, the signatures, the **token commitment**, the request nonce, and response freshness. Preview **never** redeems.

## Result copy — fixed wording, do not improvise

| Condition | Consumer result | First redemption? |
| --- | --- | --- |
| Active, valid credential, eligible | "Code matches the manufacturer's record. First verification recorded." | Yes, after confirmation |
| Inactive | "This code has not been activated by the manufacturer." | No |
| Previously redeemed | "This code was previously verified. This additional check has been recorded." | No; append repeat event |
| Unknown token | "Code not found in this system." | No |
| Expired | "The recorded expiry date has passed." | No |
| Recalled | "This batch has been recalled. View the recall details." | No |
| Blocked / suspended issuer | "Verification is restricted. Contact support." | No |
| Invalid signature / untrusted key | "Unable to validate the manufacturer's record." | No |
| Network / service unavailable | "Unable to complete verification. Please retry." | No new commit unless already committed |
| Attestation failure | "Unable to verify on this device." | No |

### Mandatory clarification on a successful result

> **"This checks the code's digital record; it does not test the medicine's contents."**

**Never** equate a first scan with "100% genuine", "safe to consume", or proof of sale. This is a patient-safety requirement, not a legal nicety — a wrongly reassuring string is the most damaging bug this app can ship.

## Offline behavior

Without connectivity, show **"Connect to check current status."** An old signed receipt **cannot** establish today's recall or redemption status. Receipts are historical evidence; they are displayed with their **original check time**, clearly labeled.

There is **no offline first redemption**.

## Localization

Bangla and English from the first release. Every string in the table above needs a reviewed Bangla translation — **by a native speaker with pharmaceutical context**, not machine translation. The distinction between "the code matches" and "the medicine is genuine" must survive translation; if it does not, the translation is wrong. See doc 15.

## Local storage

- Session credential in **protected credential storage** (Keystore / Keychain via `flutter_secure_storage`).
- Receipts stored locally, scoped to this installation.
- **No raw token in logs or crash reports.** Disable any crash reporter that captures URLs, or scrub aggressively.

## Pending confirmation state

If the backend commits but signing or delivery fails, the app shows a **pending** state and polls `POST /v1/consumer/operations/{id}/status` with a fresh nonce. It must **not** re-confirm, and must not create a second event.

## Key components

| Concern | Approach |
| --- | --- |
| QR decoding | `mobile_scanner` (camera + torch) |
| Secure storage | `flutter_secure_storage` |
| Attestation | Firebase App Check — Play Integrity (Android), App Attest (iOS) |
| **ML-DSA verification** | **Unresolved — spike S2, doc 13.** Dart FFI to bundled `libcrypto`, or a vetted pure-Dart verifier. Must pass `crypto-vectors/`. |
| Canonical JSON | RFC 8785 implementation validated against the golden vectors |

Android does not ship OpenSSL (it uses BoringSSL), so an FFI approach must **bundle** `libcrypto.so` per ABI and accept the APK size cost.
