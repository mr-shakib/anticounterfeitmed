# 16 — Glossary

| Term | Meaning in this project |
| --- | --- |
| **Unit** | One intact strip or package sold as a whole, identified by one hidden code. Not one tablet. |
| **Token** | 32 random bytes, Base64url (43 chars), printed in the QR fragment. A possession credential. |
| **Token hash** | `SHA-256(raw_token)` — the only form stored in the database. |
| **ACTIVE** | The manufacturer approved and signed the unit; it can be verified. |
| **REDEEMED** | A **first consumer verification was committed**. Permanent. **Not** a sale, delivery, or consumption. |
| **VOID** | Cancelled, damaged, or rejected. Never becomes active. |
| **Restriction** | Blocked unit, recalled batch, or suspended organization. Separate from lifecycle; overrides a positive outcome. |
| **Activation credential** | The immutable ML-DSA-signed record created at activation (context `medicine-activation-v1`). |
| **Status envelope** | A separately signed, short-lived statement of current status (context `medicine-status-v1`). |
| **Trust manifest** | Root-signed, versioned list authorizing manufacturer and service public keys. |
| **Challenge** | Short-lived value from `prepare`, bound to session, unit, action, and credential version; consumed by `confirm`. |
| **Operation** | An idempotent confirm attempt, keyed by session + idempotency key. |
| **Outbox** | Row created in the same transaction as an event, so a receipt can be signed later without undoing the event. |
| **Manufacturer-asserted record** | Printing/QC/coating completion entered by manufacturer staff — **not** automatically captured factory scan evidence. |
| **Platform-managed manufacturer-associated signature** | The honest description of a signature made with a manufacturer key held by the platform. Not proof only the manufacturer could sign. |
| **ML-DSA** | FIPS 204 signature algorithm (successor to Dilithium). Signs records. |
| **ML-KEM** | FIPS 203 key encapsulation (successor to Kyber). Establishes keys. **Does not sign.** |
| **JCS** | RFC 8785 JSON Canonicalization Scheme — makes signed bytes reproducible. |
| **Context string** | ML-DSA domain separator ensuring a signature for one purpose fails for another. |
| **App Check** | Firebase app attestation (Play Integrity / App Attest). Attests the **app**, not the user. |
| **First redemption** | The single, permanent `FIRST_REDEMPTION` event per unit, guaranteed by a partial unique index. |
| **Repeat event** | Any later confirmation on an already-redeemed unit. Recorded, flagged, never a counterfeit verdict by itself. |
