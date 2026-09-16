# 01 — Scope and Roles

Source: SRS §1, §3.3, §3.5, §11.

## The three ends we build now

| Role | Interface | Deployable |
| --- | --- | --- |
| Platform admin | Staff web portal, admin workspace | `staff-web` + `backend` |
| Manufacturer | Same portal, manufacturer workspace | `staff-web` + `backend` |
| Consumer | Flutter mobile app (Android first) | `consumer-app` + `backend` |
| General visitor | Public landing page, no verification | `landing` |

## Explicitly NOT built in this release

The SRS is emphatic about this and it is the single easiest way to blow the schedule. Do not build:

- Factory/printing/QC operator accounts, station logins, scanner integrations, or a QC scan API.
- Pharmacy accounts, registration, dashboards, stock lookup, inventory, POS, or logistics integration.
- Any `SALE_RECORDED` event or sale inference.
- Offline first redemption.
- PQC signatures embedded in the QR payload.
- Any automatic physical-authenticity verdict.
- An AI/ML model (SRS §8: "The first operational version does not need an AI model").
- iOS release, hybrid ML-KEM transport, OCR assistance — all later extensions.

Printing, QC, and scratch coating **still physically happen**. They are recorded by manufacturer staff as operational assertions in the manufacturer workspace. The software end is deferred; the physical step is not.

### Why this matters to the data model

Because these records are manufacturer-entered assertions and not captured factory scan evidence, every such record must store *both* the claimed completion time and the entry time, *plus* the recording user and a source reference — and the UI must label them as manufacturer-asserted. See doc 04, `ManufacturingCompletionEvent`.

## Role permission matrix

| Capability | Platform admin | Mfr. release manager | Mfr. staff | Consumer |
| --- | --- | --- | --- | --- |
| Approve organization | Yes | No | No | No |
| Suspend organization / key | Yes | No | No | No |
| Block a unit | Yes | Yes (own org) | No | No |
| Create product / batch | No | Yes (own) | Yes (own) | No |
| Generate print job / labels | No | Yes (own) | Yes (own) | No |
| Record printing/QC/coating | No | Yes (own) | Yes (own) | No |
| **Approve activation (sign)** | **No** | **Yes (own)** | No | No |
| Recall a batch | No | Yes (own) | No | No |
| View audit records | Yes (all) | Yes (own org) | Scoped | No |
| Investigate reports | Yes | Own products | Scoped | File only |
| Verify / redeem a unit | No | No | No | Yes |

### Hard prohibitions (must be enforced in code, not policy)

- Admin **cannot** edit signed product data.
- Admin **cannot** reset a redeemed unit to active.
- Admin **does not** routinely activate on a manufacturer's behalf.
- Manufacturer A **cannot** read or act on manufacturer B's anything. This is milestone 2's completion gate.
- Consumer credentials are never accepted on staff endpoints, and staff sessions are never accepted as a substitute for app attestation on consumer endpoints.

## The unit decision (blocking — see doc 15)

One hidden code identifies **one intact strip or package sold as a unit**. If strips are cut and tablets sold separately, the original code does not authenticate each separated portion. **The physical unit must be decided before any serial is generated**, because it is baked into every token printed.

## What the first version honestly claims

The first release claims **PQC-signed verification records**. It does **not** claim the system is fully post-quantum secure, nor that a first scan proves the medicine is genuine or safe.

Required consumer-facing clarification on every successful result:

> "This checks the code's digital record; it does not test the medicine's contents."

## Known, unresolved limitation — state it in every report

**Copying before first redemption.** Anyone who reads the QR at the factory, or after scratching, can place a copy on another package and redeem first. The first response alone cannot tell which physical package is genuine. This is addressed by physical controls, label reconciliation, scratch integrity, supply-chain evidence, and investigation — **not by ML-DSA**.

Additionally: the pilot trusts approved manufacturers' submitted product data and their self-recorded QC/coating assertions. A malicious authorized issuer can sign false data; a compromised signing service can sign false responses.
