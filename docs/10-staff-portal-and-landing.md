# 10 — Staff Portal and Landing Page

Source: SRS §2.2, §3.1, §3.2, §3.3.

## Platform admin workspace

| Feature | Required behavior |
| --- | --- |
| Organization approval | Record manufacturer identity/contact and approved issuer-key association **before** allowing production issuance |
| Access control | Organization-scoped roles; **MFA for privileged staff**; revoke when staff leave |
| Investigation queue | Filter by code-not-found reports, repeated checks, blocked units, recall reports, signing failures; assign cases; record findings |
| Emergency restriction | Suspend an organization or block a unit with a reason. **Suspension overrides a normal verification result.** |
| Audit viewer | Search by actor, organization, package, action, timestamp, request ID; export investigation evidence |
| Operational dashboard | Failed print jobs, activation failures, API errors, unresolved reports, counts of first vs. repeated verifications |

**Admin must not be able to:** edit signed product data, reset redeemed units to active, or routinely activate on a manufacturer's behalf. Investigations add a conclusion — they never erase history.

## Manufacturer workspace

| Feature | Required fields / behavior |
| --- | --- |
| Product catalog | Brand, generic, strength, dosage form, unit/pack description, manufacturer, reference packaging image, registration reference if available |
| Batch setup | Product, manufacturer batch number, manufacturing date, **explicit expiry date**, planned unit count |
| Serialization | Create unique unit IDs/tokens, controlled label export for off-system printing, count issued units |
| Manufacturing readiness | Record printed / QC-passed / rejected / coated / voided unit lists; show activation-ready quantities |
| Activation | Release manager approves **only** QC-passed, covered, unexpired units; signed credential created **before** each unit becomes active |
| Recall / block | Recall a batch or block units, with reason, effective timestamp, contact instructions |
| Results and reports | Own verification totals, repeat events, investigation cases. **No access to other manufacturers.** |

### The manufacturing-readiness screen needs care

This is the SRS's compromise for the deferred factory end, and the UI must not misrepresent it. For each completion record, capture:

1. The exact unit references (selected or uploaded).
2. Step: printed / QC-passed / coated.
3. **Actual completion time** *and* **entry time** — separate fields.
4. Recording user identity.
5. Source record/reference (the operational document this came from).
6. Result and reason.

**The UI must label these as manufacturer-asserted operational records, not automatically captured factory scan evidence.** A screen that presents them as verified scan data would misstate what the system knows.

Rejected units are recorded as **VOID**; their labels are destroyed or quarantined and **new tokens generated for replacements**.

### The codes are shown once, and that is load-bearing

Only `SHA-256(token)` is stored, so the portal can display the QR codes at the
moment it generates them and never again. That is not a missing feature: it is
what stops anyone — including a platform operator with database access —
reprinting a batch later. A label that is lost or damaged is handled by voiding
those units and generating replacements, which leaves a record.

The portal therefore renders the codes in the browser from the URLs in the
generation response, and offers a print-ready sheet at the footprint chosen for
the pilot. The CSV alongside it carries the references and URLs for
reconciliation, or for a printer that renders codes from data itself; it cannot
carry images.

### Off-system flow the portal supports

1. Staff export generated QR labels + external human-readable unit references for printing outside the platform. **External references cannot redeem units.**
2. Printing personnel do physical readability checks with existing equipment, then apply the scratch layer. **These scans do not call any platform endpoint.**
3. Staff record completion of printing, QC, and coating.
4. Rejected units recorded void.
5. The release manager activates only units whose required completion records are present.

Sample checks after coating, quantity reconciliation, and disposal of unused labels remain **operational controls outside the software**.

### Activation UI rules

- Show a clear pre-flight summary: eligible count, ineligible count **with reasons**.
- Bulk activation is a **tracked job** with per-unit success/failure counts and retry-failures-only.
- **Never** display "batch activated" when some units failed. Show partial results honestly.
- Require explicit release-manager confirmation; record actor, approval ID, activated time, credential digest, signing key ID.

## Public landing page

Separate static deployable (doc 02). Its entire job:

- Serve at `/` — **no redirect**.
- Strip the fragment via `history.replaceState` at startup, **sending it nowhere**.
- Show instructions to open the official app and rescan.
- Add verified Play Store / App Store buttons **when those listings exist**. Store links carry **no package token**.
- Contact/help information.

Hard prohibitions: **no unit verification**, no analytics, no ads, no third-party scripts, no URL-capturing error reporting, no calls to verification or redemption APIs. Restrictive CSP; `Referrer-Policy: no-referrer`.

`GET`, `HEAD`, link previews, crawlers, and prefetches **never change package state** — this is acceptance test #1 (doc 11).

## Portal technical notes

- Next.js App Router, server components for role-scoped data.
- **Authorization is enforced by the backend**, never by hiding UI. Every screen's data comes from an endpoint that re-checks object-level permissions.
- MFA enrollment flow for privileged staff.
- No third-party analytics on any route that could ever receive a token. The portal never receives tokens, but keep the dependency discipline anyway.
