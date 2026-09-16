"""The confirmation transaction.

This is the one place where a unit's redemption is decided. Two mechanisms
protect it, and both are deliberate:

* rows are locked in a fixed order -- organization, then batch, then unit -- so
  confirmation serialises against suspension, recall and blocking as well as
  against other scans. Every restriction writer must use the same order or the
  two can deadlock;
* a partial unique index permits at most one FIRST_REDEMPTION per unit, so even
  if the locking were wrong the database would still refuse a second one.

Nothing here trusts the client. The app's claim that a signature verified is
irrelevant; the server re-checks state at commit time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Batch
from apps.organizations.models import Organization
from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.verification.models import (
    ConsumerSession,
    ReceiptStatus,
    SignedReceipt,
    VerificationChallenge,
    VerificationEvent,
    VerificationEventType,
    VerificationOperation,
    VerificationOutcome,
)


class IdempotencyConflict(Exception):
    """Same idempotency key reused with a different request body."""


class ChallengeInvalid(Exception):
    """The challenge is missing, expired, already spent, or bound elsewhere."""


@dataclass(frozen=True)
class ConfirmResult:
    outcome: str
    operation: VerificationOperation
    event: VerificationEvent | None
    first_redemption: bool
    replayed: bool = False


def request_digest(payload: dict[str, Any]) -> str:
    """Stable digest of a request body, used to detect idempotency-key reuse."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _active_restrictions(
    organization: Organization, batch: Batch, unit: PackageUnit, now: datetime
) -> list[str]:
    """Restrictions that override an otherwise positive outcome."""
    restrictions: list[str] = []
    if organization.is_suspended:
        restrictions.append("ISSUER_SUSPENDED")
    if batch.is_recalled:
        restrictions.append("BATCH_RECALLED")
    if unit.is_blocked:
        restrictions.append("UNIT_BLOCKED")
    if batch.expires_on < now.date():
        restrictions.append("EXPIRED")
    return restrictions


def _outcome_for_restrictions(restrictions: list[str]) -> str:
    """Map restrictions to the outcome the consumer sees.

    Order matters: a recall is more actionable for a patient than a generic
    restriction, and expiry is the most specific of all.
    """
    if "BATCH_RECALLED" in restrictions:
        return VerificationOutcome.RECALLED
    if "EXPIRED" in restrictions:
        return VerificationOutcome.EXPIRED
    if "ISSUER_SUSPENDED" in restrictions or "UNIT_BLOCKED" in restrictions:
        return VerificationOutcome.RESTRICTED
    raise ValueError("no restriction to map")


def _resolve_existing_operation(
    session: ConsumerSession, idempotency_key: str, digest: str
) -> ConfirmResult | None:
    """Return the already-committed result for this key, if there is one.

    Raises :class:`IdempotencyConflict` when the key was reused with different
    content.
    """
    existing = VerificationOperation.objects.filter(
        session=session, idempotency_key=idempotency_key
    ).first()
    if existing is None:
        return None
    if existing.request_digest != digest:
        raise IdempotencyConflict("idempotency key reused with a different body")
    return ConfirmResult(
        outcome=existing.outcome,
        operation=existing,
        event=existing.event,
        first_redemption=(
            existing.event is not None
            and existing.event.event_type == VerificationEventType.FIRST_REDEMPTION
        ),
        replayed=True,
    )


@transaction.atomic
def confirm_verification(
    *,
    session: ConsumerSession,
    unit_id,
    challenge_id,
    idempotency_key: str,
    body: dict[str, Any],
    now: datetime | None = None,
) -> ConfirmResult:
    """Commit exactly one verification outcome for this attempt.

    Returns the existing result unchanged when the same session retries with the
    same idempotency key and body, so a timed-out request that already committed
    is never counted twice.
    """
    now = now or timezone.now()
    digest = request_digest(body)

    # 1. Idempotency first. An exact retry must resolve here, before the
    #    challenge is treated as spent.
    replay = _resolve_existing_operation(session, idempotency_key, digest)
    if replay is not None:
        return replay

    # 2. Fixed lock order: organization -> batch -> unit.
    unit_preview = PackageUnit.objects.select_related("batch__product__manufacturer").get(
        pk=unit_id
    )
    organization = Organization.objects.select_for_update().get(
        pk=unit_preview.batch.product.manufacturer_id
    )
    batch = Batch.objects.select_for_update().get(pk=unit_preview.batch_id)
    unit = PackageUnit.objects.select_for_update().get(pk=unit_id)

    # 3. Re-check idempotency now that we hold the unit lock. Concurrent
    #    retries of the same operation all pass step 1 before any of them has
    #    committed, so without this second look the losers would find the
    #    challenge already spent and fail a request that actually succeeded.
    replay = _resolve_existing_operation(session, idempotency_key, digest)
    if replay is not None:
        return replay

    # 4. The challenge must be spendable and bound to this session, unit and
    #    credential version.
    challenge = (
        VerificationChallenge.objects.select_for_update()
        .filter(pk=challenge_id, session=session, unit=unit)
        .first()
    )
    if challenge is None or not challenge.is_spendable(now):
        raise ChallengeInvalid("challenge is missing, expired or already spent")
    if challenge.credential_version != unit.version:
        raise ChallengeInvalid("unit changed since the credential was previewed")

    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at"])

    # 5. Decide the outcome from current state.
    restrictions = _active_restrictions(organization, batch, unit, now)
    event_type: str
    if restrictions:
        outcome = _outcome_for_restrictions(restrictions)
        event_type = VerificationEventType.DECLINED
    elif unit.lifecycle == UnitLifecycle.REDEEMED:
        outcome = VerificationOutcome.PREVIOUSLY_VERIFIED
        event_type = VerificationEventType.REPEAT_CHECK
    elif unit.lifecycle == UnitLifecycle.ACTIVE:
        outcome = VerificationOutcome.VERIFIED_FIRST
        event_type = VerificationEventType.FIRST_REDEMPTION
    elif unit.lifecycle == UnitLifecycle.VOID:
        outcome = VerificationOutcome.RESTRICTED
        event_type = VerificationEventType.DECLINED
    else:
        outcome = VerificationOutcome.NOT_ACTIVATED
        event_type = VerificationEventType.PREACTIVATION_ATTEMPT

    previous = (
        VerificationEvent.objects.filter(unit=unit).order_by("-server_time", "-id").first()
    )

    # 6. Commit the event. The unique index is the backstop if two transactions
    #    ever reach this point believing they are both first.
    try:
        event = VerificationEvent.objects.create(
            unit=unit,
            event_type=event_type,
            session=session,
            previous_event=previous,
            server_time=now,
            detail={"restrictions": restrictions} if restrictions else {},
        )
    except IntegrityError:
        # Another transaction won the race for the first redemption. Record this
        # attempt as the repeat check that it actually is.
        event = VerificationEvent.objects.create(
            unit=unit,
            event_type=VerificationEventType.REPEAT_CHECK,
            session=session,
            previous_event=previous,
            server_time=now,
            detail={"note": "lost first-redemption race"},
        )
        outcome = VerificationOutcome.PREVIOUSLY_VERIFIED
        event_type = VerificationEventType.REPEAT_CHECK

    if event_type == VerificationEventType.FIRST_REDEMPTION:
        unit.lifecycle = UnitLifecycle.REDEEMED
        unit.redeemed_at = now
        unit.save(update_fields=["lifecycle", "redeemed_at"])

    # 7. The receipt outbox row is created in the same transaction as the event.
    #    If signing fails afterwards, the redemption still stands.
    SignedReceipt.objects.create(event=event, status=ReceiptStatus.PENDING)

    operation = VerificationOperation.objects.create(
        session=session,
        idempotency_key=idempotency_key,
        request_digest=digest,
        unit=unit,
        outcome=outcome,
        event=event,
    )

    return ConfirmResult(
        outcome=outcome,
        operation=operation,
        event=event,
        first_redemption=event_type == VerificationEventType.FIRST_REDEMPTION,
    )
