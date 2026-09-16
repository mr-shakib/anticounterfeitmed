# 14 — Roadmap

Source: SRS §9. **Do not advance past a gate with an unresolved failure in the verification path.**

## Milestones

| # | Milestone | Work | Completion gate |
| --- | --- | --- | --- |
| 1 | Freeze protocol + spikes | Agree unit size, token URL, lifecycle, role permissions, record schema; test QR fragments on real cameras; sign on server, verify on one Android device | Same signed bytes verify across server/mobile; invalid bytes fail; printed URL opens correct website |
| 2 ✅ | Backend foundation | Organizations, MFA staff access, product/batch tables, object permissions, unit constraints, audit events | **Manufacturer A cannot access or activate manufacturer B's units** |
| 3 ✅ | Manufacturer readiness records | Generate/export labels; record off-system printing/QC/coating; reject/replace codes; reconcile quantities | Manufacturer can record required evidence and activate eligible units **without a factory end** |
| 4 ✅ | Activation and trust | Signing component, signed credentials, trust manifest, issuer binding, per-unit bulk job results | Tampered data, wrong keys, and failed signing **never** produce active eligible units |
| 5 | Consumer flow | Flutter scan/preview/confirm/result/history/report; anonymous sessions; attestation; signed statuses and receipts | Browser visits do nothing to unit state; genuine app completes one valid verification |
| 6 | Failure handling | Transactions, concurrency, outbox, retries, pending receipts, recall and suspension checks | One first redemption under contention; retry and signer-failure recovery preserve the same event |
| 7 | Physical + operational pilot | Print/scratch tests, representative phones, API load measurements, alert/case review, backup restoration | Doc 11 acceptance tests pass; issues and measured results recorded |
| 8 | Further PQC / AI experiments | Hybrid TLS measurements; then labeled OCR mismatch experiment | Negotiated algorithms evidenced; AI performance evaluated against ground truth |

**Deferred backlog, outside these milestones:** the printing/QC end and the pharmacy end. Neither is a first-release dependency. Develop either only when it is formally brought into scope.

## Estimate — and what it assumes

**10–14 full-time development weeks for one experienced developer** to reach a controlled Android pilot through milestone 7.

This is an **estimate, not a delivery guarantee**. It assumes:

- prompt manufacturer input (doc 15's blocking decisions answered quickly);
- access to cryptography review;
- packaging trials going well;
- no surprises in native crypto integration, signing-key operations, or store distribution.

Things that have historically moved this kind of estimate: packaging trials failing the 95% decode gate, Play Integrity/attestation setup, and store distribution review.

**iOS** shares Flutter UI code but needs its own native verification, attestation, and device tests before release. It is not in the 10–14 weeks.

### Where the estimate is most likely to be wrong

| Risk | Effect | Mitigation |
| --- | --- | --- |
| Dart ML-DSA verification is hard (spike S2) | +1–3 weeks | Resolve in week 0, before anything depends on it |
| Physical QR fails the 95%/3s gate | +1–4 weeks, possibly repackaging | Run the physical test early, in parallel with backend work — it needs no software |
| Play Integrity / store distribution friction | +1–2 weeks | Start the Play Console setup during milestone 2, not milestone 5 |
| Bangla clinical-safety translation review | Days–weeks of calendar time | Commission it during milestone 2 |
| Manufacturer partner unavailable for real batch data | Blocks milestone 7 | Escalate now (doc 15) |

**The physical QR test, the Play Console setup, and the Bangla translation are calendar-time items with little developer-time cost. Start all three early** — they parallelize, and each can otherwise block the pilot at the end.

## Suggested sequencing

```text
Week 0      S1, S2, S3 spikes. Blocking decisions answered.
Week 1–2    Milestone 2. In parallel: start Play Console; commission Bangla translation.
Week 3–4    Milestone 3. In parallel: print first physical test labels.
Week 5–6    Milestone 4. Signer hardening, trust manifest, key custody + recovery drill.
Week 7–9    Milestone 5. Flutter app end to end.
Week 10–11  Milestone 6. Concurrency, outbox, recovery. Full doc 11 suite.
Week 12–14  Milestone 7. Physical pilot, load measurement, backup restore drill, buffer.
Later       Milestone 8. Hybrid TLS; then OCR, only with labeled ground truth.
```

## On the AI component

The first operational version **needs no AI model**. It needs reliable serialization, state transitions, and signed verification.

The first useful AI feature is **packaging-text mismatch assistance**, and only later:

1. Ask for a photo of the printed batch/expiry area **only when investigating a concern**.
2. OCR the batch number, expiry, brand/strength.
3. Compare with the signed record.
4. Show "Printed information may not match the record" or "Image unclear", **with human review**.

**OCR must never mark a medicine genuine or alter redemption.**

Before deploying: manually label **≥300 packaging images from ≥10 batches** (clear, blurred, reflective, mismatched). Obtain manufacturer/physical-document ground truth, **split by batch**, and measure field extraction accuracy, mismatch recall, false alerts, and failure-to-read rate against manual review. **Label synthetic mismatches separately from confirmed counterfeit examples.** These are minimum pilot numbers — not sufficient evidence for a broad medical-authenticity model.

Meanwhile, collect optional consented packaging images through concern reports so the later experiment has data. Keep deterministic repeat-scan rules as the baseline; **scan repetition alone is not a counterfeit label.**
