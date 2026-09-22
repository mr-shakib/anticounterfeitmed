# 11 — Testing and Acceptance

Source: SRS §10. **Do not advance past a milestone gate with an unresolved failure in the verification path.**

## 11.1 Mandatory correctness tests

Every one of these is a blocking gate. Automate all except the physical tests.

| Test | Pass condition |
| --- | --- |
| Public URL safety | Camera opening, GET/HEAD, prefetch, and reload cause **zero** redemption events |
| App-only API controls | Missing/invalid attestation or session cannot retrieve protected details or confirm |
| Role isolation | Unrelated manufacturers and public callers cannot activate/redeem; factory/pharmacy roles and endpoints are **not exposed** |
| Lifecycle | Printing/QC/coating prerequisites enforced; voided or redeemed units cannot be reset through normal APIs |
| **QR binding** | A valid credential from **another unit** fails when paired with this token |
| Signature checks | Modified payload, wrong issuer, unknown/revoked key, **wrong context**, truncated signature all fail |
| Freshness | Old nonce, stale signed response, expired challenge, **manifest rollback** all rejected |
| **Race test** | **100 concurrent eligible attempts → exactly one first-redemption event**; others classified correctly |
| **Retry test** | 100 retries of one operation do not inflate first or repeat counts |
| Post-commit failure | Drop the connection or stop the signer after commit; recovery returns **the same event**, no rollback, no duplicate |
| Recall race | Concurrent recall/confirmation follows transaction ordering; subsequent status **always** exposes the recall |
| Privacy | Logs and reports contain **no raw QR/session tokens**; users cannot read another session's history |
| Restore | Restore a backup in isolation; known redeemed units **stay redeemed**; signed records still verify |

## 11.2 Physical QR test

Manual packaging/consumer-scanning tests. **This does not require building a printing/QC interface.**

Design:

- Sizes: **20 mm and 25 mm** total label footprint (subject to actual strip space), **including the required clear border**.
- Error correction: **M and Q**.
- **No logo inside the QR.**
- **20 distinct labels per size/EC combination = 80 labels**, printed on the **actual packaging material**.
- Check decoding **before** coating.
- Apply the **real scratch layer**, scratch normally, then test with **3 representative phones** in **3 documented conditions**: normal indoor light, low light, reflective/angled.
- **80 × 3 × 3 = 720 post-scratch trials.** Repeat for every additional packaging material in the pilot.

Record for each trial: success/failure, time to decode, phone, material, size, error correction, lighting.

### Measured module sizes for the label symbol (2026-09-22)

Since D21 the symbol carries the public URL (31 characters) plus a hidden record holding the token as 32 raw bytes — 68 data codewords in all (doc 09). That fixes the symbol version, and therefore the module size at a given footprint:

| Footprint | EC | Version | Modules incl. quiet zone | **Module size** |
| --- | --- | --- | --- | --- |
| 20 mm | M | 5 | 45 | 0.444 mm |
| 20 mm | Q | 6 | 49 | **0.408 mm** |
| 25 mm | M | 5 | 45 | 0.556 mm |
| 25 mm | Q | 6 | 49 | 0.510 mm |

Production prints **version 6 / Q** only; the M row exists for the comparison the SRS asks for. The previous URL format needed version 7 at Q (53 modules, 0.377 mm at 20 mm), so the hidden-record format is also the larger module.

**The tension that remains.** A scratched coating damages the symbol, which argues for Q. But at a fixed footprint Q still costs a version over M, and the 20 mm / Q cell is the most print-sensitive in the matrix. It is also the cell the scratch layer most needs. Test it first; if it fails, the realistic choice is a 25 mm footprint.

**Two additions to the physical test for this format.** On each phone, scan a label with the default camera app and one third-party QR app and confirm they show **only** `https://anticounterfeitmed.com/`. Then scan the same labels with the consumer app and confirm it reads the token — this is the on-device check that ML Kit reports the full data codewords on that phone, which the format depends on.

Generate the sheet with `make labels`.

**Starting release gate: ≥95% decoding within 3 seconds in each supported ordinary-use condition.** If real packaging fails, improve printing/size/coating and retest before rollout. This is a project target, not a universal QR guarantee.

## 11.3 Performance and research measurements

Use **10,000 synthetic units and isolated test keys**. **Exclude synthetic events from production dashboards and fraud labels** — this matters, or the pilot's own load test will pollute its counterfeit signals.

Measure separately:

- QR decode time (reported separately, **outside** the service target)
- Activation signing throughput
- App signature-verification time
- prepare/confirm latency
- Receipt-signing delay
- Response bytes
- First/repeat outcome accuracy
- Attestation-related failures

Report **p50/p95** with phone models, server configuration, library versions, network conditions, and test scripts.

**Starting service target: p95 under 2 seconds from confirmation tap to verified receipt at 20 confirmation requests/second, on a documented test network. Measure it — do not promise it before testing.**

### First response-size measurements (2026-09-17, local HTTP)

Taken against the real server, not estimated. Base64 inflates the signatures by roughly a third.

| Endpoint | Response bytes |
| --- | --- |
| `prepare` | **~11.0 KB** |
| `confirm` | ~5.5 KB |
| `GET /v1/trust/manifest` | ~11.1 KB (3 keys) |

`prepare` carries two ML-DSA-65 signatures (activation credential and status envelope) plus the credential itself, and dominates the flow. This matters on the networks the pilot targets: on a slow mobile connection, 11 KB is the difference between a scan that feels instant and one that does not. Two levers exist if it proves too slow — benchmark ML-DSA-44, whose signatures are smaller (decision D6), and return the signatures as raw bytes rather than base64. Measure before changing anything.

The trust manifest grows with every key, so its size should be re-measured once a realistic number of manufacturers exist.

### PQC comparison (for the research output)

Run the same canonical record and workflow with:

- a classical signature baseline (e.g. Ed25519),
- ML-DSA-44,
- ML-DSA-65.

Compare **byte overhead and end-to-end latency**, not just cryptographic microbenchmarks. Known reference points already measured here: ML-DSA-65 signature = 3,309 bytes, public key = 1,952 bytes.

**Implementing standard algorithms in this workflow does not by itself establish novelty.** The defensible contributions are the measurements, the workflow integration, and the honest limitation analysis.

## Test infrastructure

| Layer | Approach |
| --- | --- |
| Backend unit/integration | `pytest` + `pytest-django`, real PostgreSQL (not SQLite — partial unique indexes and row locks must be exercised) |
| Race tests | Real concurrent clients against a real database; `SELECT … FOR UPDATE` behavior cannot be faked |
| Crypto | Golden vectors in `crypto-vectors/`, run by backend, signer, Dart, and the OpenSSL CLI cross-check |
| API contract | Schema snapshot tests; contract tests shared with the Flutter client |
| Flutter | Widget tests + integration tests on a real Android device for verification and attestation |
| Frontend | Component tests; authorization tested at the API, not the UI |

**CI must fail on:** a crypto vector mismatch, a race-test failure, or any log line matching a 43-character Base64url token pattern.
