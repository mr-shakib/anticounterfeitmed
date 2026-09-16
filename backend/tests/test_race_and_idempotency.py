"""Concurrency and idempotency guarantees (docs/11 race and retry tests).

These use ``transaction=True`` so each thread commits for real. Without it the
whole test would run inside one rolled-back transaction and the race would never
happen.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import connections
from django.utils import timezone

from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.verification.models import (
    VerificationEvent,
    VerificationEventType,
    VerificationOperation,
    VerificationOutcome,
)
from apps.verification.services import (
    IdempotencyConflict,
    confirm_verification,
)
from tests.conftest import make_session_and_challenge

CONCURRENCY = 100


def _run_concurrently(targets):
    """Run callables on separate threads, each with its own DB connection."""
    results: list = []
    errors: list = []
    lock = threading.Lock()
    barrier = threading.Barrier(len(targets))

    def runner(fn):
        try:
            # Maximise real contention: every thread arrives together.
            barrier.wait(timeout=30)
            outcome = fn()
            with lock:
                results.append(outcome)
        except Exception as exc:  # noqa: BLE001 - recorded and asserted on below
            with lock:
                errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=runner, args=(fn,)) for fn in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results, errors


@pytest.mark.django_db(transaction=True)
def test_exactly_one_first_redemption_under_contention(batch):
    """100 distinct eligible confirmations must yield exactly one redemption."""
    from tests.conftest import make_active_unit

    unit, _token = make_active_unit(batch)

    prepared = [make_session_and_challenge(unit) for _ in range(CONCURRENCY)]

    def attempt(session, challenge):
        def run():
            return confirm_verification(
                session=session,
                unit_id=unit.id,
                challenge_id=challenge.id,
                idempotency_key=f"key-{session.id}",
                body={"unit": str(unit.id)},
            )

        return run

    results, errors = _run_concurrently([attempt(s, c) for s, c in prepared])

    assert not errors, f"unexpected errors: {errors[:3]}"
    assert len(results) == CONCURRENCY

    firsts = [r for r in results if r.first_redemption]
    repeats = [r for r in results if r.outcome == VerificationOutcome.PREVIOUSLY_VERIFIED]

    assert len(firsts) == 1, f"expected exactly one first redemption, got {len(firsts)}"
    assert len(repeats) == CONCURRENCY - 1

    # The database must agree with the returned results.
    assert (
        VerificationEvent.objects.filter(
            unit=unit, event_type=VerificationEventType.FIRST_REDEMPTION
        ).count()
        == 1
    )
    assert VerificationEvent.objects.filter(unit=unit).count() == CONCURRENCY

    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.REDEEMED
    assert unit.redeemed_at is not None


@pytest.mark.django_db(transaction=True)
def test_retries_do_not_inflate_counts(batch):
    """100 retries of one operation must commit exactly one event."""
    from tests.conftest import make_active_unit

    unit, _token = make_active_unit(batch, reference="UNIT-RETRY")
    session, challenge = make_session_and_challenge(unit)
    body = {"unit": str(unit.id)}

    def attempt():
        return confirm_verification(
            session=session,
            unit_id=unit.id,
            challenge_id=challenge.id,
            idempotency_key="stable-key",
            body=body,
        )

    results, errors = _run_concurrently([attempt for _ in range(CONCURRENCY)])

    assert not errors, f"unexpected errors: {errors[:3]}"
    assert VerificationEvent.objects.filter(unit=unit).count() == 1
    assert VerificationOperation.objects.filter(session=session).count() == 1

    firsts = [r for r in results if r.first_redemption]
    assert len(firsts) == CONCURRENCY, "every retry should report the same committed event"
    assert len({r.event.id for r in results}) == 1, "all retries must cite one event"


@pytest.mark.django_db(transaction=True)
def test_same_key_different_body_conflicts(batch):
    from tests.conftest import make_active_unit

    unit, _token = make_active_unit(batch, reference="UNIT-CONFLICT")
    session, challenge = make_session_and_challenge(unit)

    confirm_verification(
        session=session,
        unit_id=unit.id,
        challenge_id=challenge.id,
        idempotency_key="shared-key",
        body={"unit": str(unit.id)},
    )

    with pytest.raises(IdempotencyConflict):
        confirm_verification(
            session=session,
            unit_id=unit.id,
            challenge_id=challenge.id,
            idempotency_key="shared-key",
            body={"unit": "a-different-unit"},
        )


@pytest.mark.django_db(transaction=True)
def test_recall_before_confirmation_declines(batch):
    """A recall that commits first must decline the confirmation."""
    from tests.conftest import make_active_unit

    unit, _token = make_active_unit(batch, reference="UNIT-RECALL")
    session, challenge = make_session_and_challenge(unit)

    batch.is_recalled = True
    batch.recalled_at = timezone.now()
    batch.recall_notice = "Packaging defect"
    batch.save(update_fields=["is_recalled", "recalled_at", "recall_notice"])

    result = confirm_verification(
        session=session,
        unit_id=unit.id,
        challenge_id=challenge.id,
        idempotency_key="recall-key",
        body={"unit": str(unit.id)},
    )

    assert result.outcome == VerificationOutcome.RECALLED
    assert not result.first_redemption
    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.ACTIVE, "a declined attempt must not redeem"


@pytest.mark.django_db(transaction=True)
def test_confirmation_before_recall_keeps_history_and_shows_recall(batch):
    """A redemption that commits first survives a later recall, and both show."""
    from tests.conftest import make_active_unit

    unit, _token = make_active_unit(batch, reference="UNIT-ORDER")
    session, challenge = make_session_and_challenge(unit)

    result = confirm_verification(
        session=session,
        unit_id=unit.id,
        challenge_id=challenge.id,
        idempotency_key="order-key",
        body={"unit": str(unit.id)},
    )
    assert result.first_redemption

    batch.is_recalled = True
    batch.recalled_at = timezone.now()
    batch.save(update_fields=["is_recalled", "recalled_at"])

    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.REDEEMED, "the verification stays in history"
    assert unit.batch.is_recalled, "and the recall is visible alongside it"
