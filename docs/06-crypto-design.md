# 06 — Cryptography Design

Source: SRS §6. **ML-DSA signs. ML-KEM establishes encryption keys. ML-KEM does not sign records and does not encrypt QR/product content.**

Use the standardized names and implementations — ML-DSA (FIPS 204) and ML-KEM (FIPS 203), the standardized successors of Dilithium and Kyber. Do not assume old Dilithium/Kyber implementations produce interchangeable artifacts.

## Where PQC belongs

| Location | Mechanism | Priority |
| --- | --- | --- |
| Manufacturer activates a unit | ML-DSA-65 signature on the activation credential | Core pilot |
| Backend returns status / receipt | ML-DSA-65 signature binding nonce, time, status, event | Core pilot |
| App receives issuer/service keys | Root-signed ML-DSA trust manifest | Required with signatures |
| Client → API transport | TLS 1.3 hybrid group, e.g. `X25519MLKEM768` | Next phase |
| Long-term audit exports | Signed checkpoint/export | When evidence exports are used |
| QR printing, coating, DB redemption | Random tokens, physical controls, permissions, transactions | **Not PQC's job** |

ML-DSA-65 is a **proposed starting parameter**, not a requirement. Benchmark ML-DSA-44 vs 65 before fixing production policy (doc 11).

## Verified implementation facts (measured 2026-09-16)

```text
Library:  cryptography 50.0.1  (bundles OpenSSL 4.0.2)
Module:   cryptography.hazmat.primitives.asymmetric.mldsa
Classes:  MLDSA44/65/87 PrivateKey / PublicKey;  mlkem: MLKEM768/1024

ML-DSA-65 signature ......... 3309 bytes   (matches FIPS 204 Table 2)
ML-DSA-65 public key ........ 1952 bytes
ML-DSA-65 private key ....... 32 bytes (raw seed)
context= parameter .......... supported and ENFORCED
Cross-check: system OpenSSL 3.5.5 lists ML-DSA-44/65/87 and produced
             an identical 3309-byte signature via the CLI.
```

Negative tests that passed (all raised `InvalidSignature`): wrong context, empty context, tampered message.

Because signatures are 3,309 bytes, **they stay in the API response** — never in the printed QR. A QR carrying a signature would need a much denser/larger symbol.

## Canonicalization and domain separation

1. Build the record as JSON.
2. Canonicalize with **RFC 8785 JCS** (`rfc8785` on PyPI; the Dart side needs a matching implementation validated against the golden vectors).
3. Sign the **canonical bytes** with an explicit ML-DSA **context string**.
4. Transmit **those exact bytes** plus a detached signature.
5. The verifier checks the signature **on the received bytes before parsing or displaying them**.
6. Reject duplicate JSON keys and invalid schema types.

Context strings separate uses and are mandatory:

| Record | Context string |
| --- | --- |
| Activation credential | `medicine-activation-v1` |
| Status / result envelope | `medicine-status-v1` |
| Trust manifest | `medicine-trust-manifest-v1` |

A signature made for one context must fail verification under another. **This is library-enforced — verified above.**

## Activation credential

Signed at activation, immutable thereafter (SRS §6.2 schema illustration — not a test vector):

```json
{
  "schema": "medicine-activation-v1",
  "algorithm": "ML-DSA-65",
  "key_id": "manufacturer-key-identifier",
  "manufacturer_id": "manufacturer-identifier",
  "package_id": "unit-identifier",
  "token_sha256": "hex-digest-of-the-raw-token",
  "product_snapshot": {
    "brand": "…", "generic": "…", "strength": "…",
    "dosage_form": "…", "pack_description": "…"
  },
  "batch_number": "…",
  "manufactured_on": "YYYY-MM-DD",
  "expires_on": "YYYY-MM-DD",
  "qc_event_id": "…",
  "coating_event_id": "…",
  "activation_approval_id": "…",
  "activated_at": "UTC-timestamp",
  "record_version": 1
}
```

Add **any displayed manufacturer identity/registration field** to the signed snapshot. If the reference image is presented as authenticated, include its digest; otherwise label it in the UI as illustrative.

### Binding checks — a valid signature is not enough

On both app and backend, verify that:

- the signed `token_sha256` **matches the scanned token**;
- the key is **authorized for this manufacturer**;
- the credential **belongs to the requested unit**.

**A valid signature on some other package must fail.** This is an explicit acceptance test (doc 11, "QR binding").

## Dynamic status is separate from the static credential

A static signature cannot know that a later scan, block, or recall happened. So status is signed **separately**, containing: schema, key id, package id / token commitment, activation-credential digest, lifecycle, applicable restrictions, outcome, operation/event id, **request nonce**, server issue time, expiry time.

The app validates its **expected nonce**, permitted response age, key purpose, package binding, and signature.

Two honest limits to keep in project claims:

- Stored receipts are **historical evidence**; refreshing status is still required.
- A valid signature authenticates **the signing service's statement**, not the correctness of every database operation behind it.

## Key custody and trust

- **Separate keys** per manufacturer (activation) and for the platform status/receipt service.
- Private keys never appear in: the mobile app, the QR, the JavaScript bundle, ordinary database rows, or the source repository. `SigningKey` stores a **reference only**.
- The app ships with an **offline root public key**. Root-signed, **versioned** manifests authorize manufacturer and service keys with purpose, validity, and revocation status.
- Require a fresh manifest for online verification. Cache limit 24 h; refresh immediately on unknown/revoked-key errors. **Prevent rollback** to a manifest version already superseded on that installation.
- Retired keys may remain valid for historical credentials per policy. Compromised/revoked keys trigger a **verification hold** plus human review — never silent trust of old signatures.
- Because the private key is a **32-byte seed**, wrap it in a KMS/secret manager and give the signer process decrypt-on-start access only.

### The honesty requirement

In the pilot the platform holds the manufacturer keys. Therefore describe the output as a **platform-managed manufacturer-associated signature** — *not* independent proof that only the manufacturer could sign. Independent custody requires manufacturer-operated signing infrastructure. Do not assume any existing HSM/KMS supports ML-DSA without checking that exact product.

Key-manifest freshness **limits detection** of revocation; it does not make revocation instantaneous. A compromised offline root requires a separately authenticated app/trust update. Back up signing keys and **verify recovery before issuance**.

## `crypto-vectors/` — the real contract

The interoperability contract is a committed fixture set, not a library choice:

```text
crypto-vectors/
├── activation/        canonical bytes, signature, public key, key id, expected: VALID
├── status/            same, context medicine-status-v1
├── manifest/          root-signed manifest samples
└── negative/          tampered byte, wrong context, wrong key, truncated sig,
                       duplicate JSON key, wrong token binding → expected: INVALID
```

Every implementation — Django, signer, Dart, and the OpenSSL CLI cross-check — runs these in CI. **Milestone 1's gate is: the same signed bytes verify across server and mobile, and invalid bytes fail everywhere.**

## Transport (next phase, not now)

Test one controlled service/client connection using the library's TLS 1.3 hybrid group (e.g. `X25519MLKEM768`). **Record the actual negotiated group**, handshake latency, and bytes. Extend to mobile only after its transport stack supports it — Dart's normal TLS client does **not** automatically gain PQC because the server uses OpenSSL.

Use the library's protocol implementation. Do **not** design a custom Kyber handshake or put static keys in the QR. Hybrid key exchange does not replace classical TLS certificates or app attestation. **Label fallback-to-classical connections as such, and make PQC-specific experiments fail rather than silently fall back.** The TLS endpoint terminates protection; upstream connections need their own.

## What the first release may claim

**"PQC-signed verification records."** Not "fully post-quantum secure." Implementing standard algorithms in this workflow does not by itself establish research novelty.
