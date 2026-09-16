# 08 — Concurrency and Failure Handling

Source: SRS §4.4. This is where correctness is won or lost. PostgreSQL is the authority.

## The confirm transaction

Inside one transaction:

1. **Resolve the idempotency record first.** An exact retry returns the existing operation **before** the challenge is treated as spent.
2. **Lock rows in a fixed order**: organization/key → batch → unit. **Every restriction writer (suspend, recall, block) uses the same order.** This serializes confirmation against suspension, recall, and unit blocking as well as against competing scans.
3. Recheck current restrictions and credential validity. **Never** trust the app's claim that a signature passed.
4. **Consume the challenge in the same transaction as the event.**
5. Commit exactly one of: first redemption, repeat-check event, or declined attempt.
6. **Create the receipt-signing outbox entry in the same transaction as the event.**

The guarantee comes from the partial unique index (doc 04), not from application logic:

```sql
CREATE UNIQUE INDEX one_first_redemption_per_unit
    ON verification_event (unit_id)
    WHERE event_type = 'FIRST_REDEMPTION';
```

Two eligible confirmations arriving together → **one first redemption and one repeat outcome.**

## Idempotency behavior

| Case | Result |
| --- | --- |
| Same session + key + same body | Return existing operation |
| Same session + key + different body | `409 Conflict` |
| Reopening history | No new event |
| Retrying a timed-out request | No new event |

## Post-commit failure — never undo a redemption

If signing or response delivery fails **after** commit:

- **Do not undo the redemption.**
- The app shows a **pending confirmation** state and polls the operation endpoint.
- The worker signs the committed event from the outbox.
- Recovery returns **the same event** with a **fresh nonce-bound status envelope**.
- **Workers are idempotent.**

## Ordering between recall and confirmation

- Recall commits first → confirmation is **declined**.
- Confirmation commits first → history **retains that verification**, and subsequent reads **always show the recall**.

Both facts remain visible. A redeemed unit can later be recalled.

## Bulk activation

- A **tracked job** with per-unit success/failure counts.
- **Retry only failures.**
- **Never** report a whole batch as active when some units failed signing or validation.
- A unit with **no valid credential remains inactive**.
- Publish the credential and flip `COVERED → ACTIVE` **together**, after rechecking that the approved snapshot/version has not changed.

## Backup and recovery

- PostgreSQL **continuous WAL archiving / PITR** plus encrypted daily backups.
- **Verify restoration** — untested backups do not count.
- **Database recovery must not reopen spent codes.** Restore in isolation and confirm known redeemed units stay redeemed and signed records still verify (acceptance test, doc 11).
- If acknowledged events cannot be recovered after an incident, **hold verification for affected units until reconciled** — never treat them as unredeemed.

## Required load/race tests

See doc 11. Minimum: 100 concurrent eligible attempts → exactly one first redemption; 100 retries of one operation → no inflated counts; kill the signer after commit → recovery returns the same event.
