# 10 — Staff Portal and Landing Page

Source: SRS §2.2, §3.1, §3.2, §3.3.

## Platform admin workspace

| Feature | Required behavior |
| --- | --- |
| Organization approval | Record manufacturer identity/contact and approved issuer-key association **before** allowing production issuance |
| Access control | Organization-scoped roles; **MFA for privileged staff** (see below); revoke when staff leave |
| Investigation queue | Filter by code-not-found reports, repeated checks, blocked units, recall reports, signing failures; assign cases; record findings |
| Emergency restriction | Suspend an organization or block a unit with a reason. **Suspension overrides a normal verification result.** |
| Audit viewer | Search by actor, organization, package, action, timestamp, request ID; export investigation evidence |
| Operational dashboard | Failed print jobs, activation failures, API errors, unresolved reports, counts of first vs. repeated verifications |

### Second factor: opt-in by default, compulsory by policy

Staff enrol a second factor from Settings when they choose to; signing in does
not push anyone through enrolment. Once enrolled it is always demanded at
sign-in, whatever the policy says — otherwise enrolling would achieve nothing,
since an attacker holding the password would simply not present a code.

`STAFF_MFA_REQUIRED=1` makes enrolment a precondition for privileged roles, and
that is what this document and the SRS ask for. **Set it before the pilot.** A
release manager can put medicine into circulation and an admin can suspend an
issuer; a password alone is thin protection for either, particularly one that
has been reused elsewhere.

Removing a factor needs a current code, so an unattended screen cannot be used
to strip the protection off an account, and it is audited. Where policy makes it
compulsory, removal is an administrator action instead.

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

### Label runs, and how long the codes last

Only `SHA-256(token)` is kept permanently, so the codes cannot be recovered from
the database. But discarding them the moment a page closes is not what the SRS
asks for either: it keeps encrypted print artifacts until a job is reconciled
and deletes them within 24 hours.

So a print job retains its export, encrypted, and the batch page lists its runs
with the labels still attached. A manufacturer who navigates away, or comes back
the next morning, can open the codes again. Reconciling the job — recording how
many were printed and how many rejected — shortens the retention to the grace
period, because once quantities are agreed there is no further reason to hold
raw tokens. A job that is never reconciled expires at a longer ceiling rather
than keeping them indefinitely.

Once the export is deleted the codes are gone, and replacing lost labels means
voiding those units and issuing new ones, which leaves a record. Deletion is
recorded on the job, so disposal of an artifact holding raw tokens is visible.

The codes are rendered in the browser and offered three ways: printed straight
away, downloaded as a self-contained HTML sheet, or downloaded as a ZIP of one
SVG per unit for label software. The CSV alongside them carries references and
URLs for reconciliation; it cannot carry images.

### Footprint and whether a label can actually be read

The printed URL fixes the symbol at 53 modules across including the quiet zone,
so the footprint alone decides how wide a module is. The portal shows that figure
as the size is chosen, because the smaller options cannot work: at 5 mm a module
is 0.094 mm, far below what a phone camera resolves, and a run printed at that
size would be unreadable. Sizes from 15 mm are usable, 20 mm and above
comfortably so.

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
