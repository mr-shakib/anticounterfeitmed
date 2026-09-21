# 05 — API Contract

Source: SRS §5.3, §4.3. All paths are proposed contracts; organization- and object-level authorization is **mandatory on every staff endpoint**.

## Authority rules

- Consumer endpoints require **both** a consumer session credential **and** a valid Firebase App Check token. Never one or the other.
- Consumer endpoints **never** accept a staff session as a substitute for app attestation.
- Staff endpoints **never** accept a consumer credential as authority.
- A header like `X-Our-App: true`, an embedded API key, CORS config, or a user-agent string **is not authorization**.
- `GET`/`HEAD`, link previews, crawlers, and prefetches **never** change package state.

## Endpoints

| Method and path | Caller | Behavior |
| --- | --- | --- |
| `GET /` | Public | Landing/help page only. No verification. |
| `POST /v1/consumer/sessions` | Attested app | Create anonymous consumer session |
| `GET /v1/trust/manifest` | App | Root-signed issuer/service public-key manifest |
| `POST /v1/products` | Manufacturer | Create product |
| `POST /v1/batches` | Manufacturer | Create batch |
| `POST /v1/print-jobs` | Manufacturer | Generate serials/tokens + controlled label export |
| `POST /v1/print-scans` | Authorized mfr. staff | Read one printed code back on the line. Takes a **raw token**, stores only its digest, and records `PRINTED` as scan evidence. Refused once a unit is past `CREATED`. |
| `POST /v1/manufacturing-confirmations` | Authorized mfr. staff | Record printed/QC/coated for a whole batch or an exact unit list, with completion time + source reference |
| `POST /v1/activation-jobs` | Mfr. release manager | Approve / sign / activate eligible units |
| `GET /v1/activation-jobs/{id}` | Authorized mfr. | Per-unit results and failure counts |
| `POST /v1/consumer/verifications/prepare` | Attested session | Fetch signed info/status; issue challenge. **Does not redeem.** |
| `POST /v1/consumer/verifications/confirm` | Attested session | Commit first or repeat check, idempotently |
| `POST /v1/consumer/operations/{id}/status` | Owning session | Recover result with fresh nonce. **No new check.** |
| `POST /v1/consumer/packages/status` | Attested session | Refresh known package. **No redemption.** |
| `POST /v1/reports` | Consumer or scoped staff | Create concern report; accept external refs when token unavailable |
| `GET /v1/reports/{id}` | Reporter or assigned reviewer | Read permitted case fields |
| `POST /v1/batches/{id}/recall` | Mfr. release manager | Publish recall; prevent later first redemptions |
| `POST /v1/units/{id}/block` | Authorized mfr./admin | Restrict unit with audited reason |

Add scoped listing/detail and account-management routes required by the screens (doc 10).

**Deferred — do not implement:** factory station endpoints, automated QC scan endpoints, pharmacy lookup endpoints.

## The two-step verification flow

Per SRS §4.3. The split exists so that **previewing never redeems**.

```mermaid
sequenceDiagram
    participant App
    participant API
    participant DB
    participant Signer

    App->>App: Decode URL locally; accept only HTTPS,<br/>exact host, expected version, valid 32-byte token
    App->>API: POST prepare {token, nonce, session, attestation}
    API->>DB: hash token, load unit, check record
    API->>Signer: sign status envelope (medicine-status-v1)
    API-->>App: activation credential + signed status + challenge
    App->>App: Verify trusted key, signatures, token commitment,<br/>nonce, freshness — THEN display
    Note over App: Consumer taps "Verify this package"
    App->>API: POST confirm {challenge, fresh nonce, idempotency key}
    API->>DB: TX: lock org→batch→unit, recheck restrictions,<br/>consume challenge, commit event + outbox
    API->>Signer: sign result (async via outbox if needed)
    API-->>App: signed result bound to this request + event
    App->>App: Verify, store receipt locally
```

Critical rules:

- The backend **never trusts the app's claim that a signature passed**. It re-checks everything server-side.
- Inactive units expose **only limited status** in `prepare`.
- The challenge is bound to session, unit, intended action, **and previewed credential version**.

## Freshness parameters (pilot starting values)

These are **pilot settings to test on slow connections**, not properties of ML-DSA. Tune them with real Bangladesh network measurements.

| Parameter | Starting value |
| --- | --- |
| Challenge lifetime | 120 s |
| Status/result envelope lifetime | 120 s |
| Trust manifest cache | 24 h, immediate refresh on unknown/revoked-key error |
| Rate limit — prepare | 30 / minute / session |
| Rate limit — confirm | 10 / minute / session |

Broader IP-based controls must be tuned for **shared pharmacy and mobile networks** — many genuine users behind one NAT is normal here. **Rate-limit failures are not counterfeit labels.**

## Idempotency

`confirm` requires a stable idempotency key per attempt.

| Case | Response |
| --- | --- |
| Same session + key + same request body | Return the existing operation |
| Same session + key + **different** body | `409 Conflict` |
| Retry after timeout | Resolved via the idempotency record before treating the challenge as spent |

100 retries of one operation must not inflate first or repeat counts (SRS §10.1).

## Error and outcome model

Outcomes are **server-decided**, returned inside the signed status/result envelope. Consumer-facing wording is fixed in doc 09 — do not improvise copy.

| Outcome | First redemption recorded? |
| --- | --- |
| `VERIFIED_FIRST` | Yes, after confirmation |
| `NOT_ACTIVATED` | No |
| `PREVIOUSLY_VERIFIED` | No — append repeat event |
| `NOT_FOUND` | No |
| `EXPIRED` | No |
| `RECALLED` | No |
| `RESTRICTED` (blocked unit / suspended issuer) | No |
| `INVALID_CREDENTIAL` | No |
| `SERVICE_UNAVAILABLE` | No new commit unless the earlier request already committed |

Transport-level errors use standard HTTP codes; **verification outcomes are not HTTP errors** — a `NOT_FOUND` token still returns `200` with a signed envelope, so the app can verify the signature on the negative answer too.

## Envelope shapes

Every signed response carries, at minimum: schema, key id, package id / token commitment, activation-credential digest, lifecycle, applicable restrictions, outcome, operation/event id where applicable, **request nonce**, server issue time, expiry time. See doc 06.
