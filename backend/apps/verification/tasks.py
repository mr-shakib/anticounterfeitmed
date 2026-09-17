"""Background work for the verification flow.

The receipt outbox exists so that a signing or delivery failure after commit
never undoes a redemption. The event is already durable; a worker signs it
afterwards, and the app polls until the receipt is ready.

Every task here is idempotent. A receipt that is already signed is left alone,
so a retried or duplicated job cannot produce a second signature or a second
event.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.verification.models import ReceiptStatus, SignedReceipt

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 10


def sign_one_receipt(receipt_id) -> bool:
    """Sign a single pending receipt. Returns True when it ends up signed.

    Safe to call repeatedly: an already-signed receipt is a no-op.
    """
    from apps.verification.envelopes import new_nonce, sign_status

    with transaction.atomic():
        receipt = (
            SignedReceipt.objects.select_for_update()
            .select_related("event__unit")
            .get(pk=receipt_id)
        )
        if receipt.status == ReceiptStatus.SIGNED:
            return True

        event = receipt.event
        unit = event.unit
        credential = getattr(unit, "activation_credential", None)

        try:
            envelope = sign_status(
                unit=unit,
                outcome=_outcome_for_event(event),
                restrictions=event.detail.get("restrictions", []),
                request_nonce=new_nonce(),
                credential_digest=credential.credential_digest if credential else None,
                event_id=str(event.id),
            )
        except Exception as exc:  # noqa: BLE001 - recorded, retried, never fatal
            receipt.attempts += 1
            receipt.last_error = str(exc)
            receipt.status = (
                ReceiptStatus.FAILED
                if receipt.attempts >= MAX_ATTEMPTS
                else ReceiptStatus.PENDING
            )
            receipt.save(update_fields=["attempts", "last_error", "status"])
            logger.warning("receipt %s signing failed: %s", receipt_id, exc)
            return False

        receipt.canonical_bytes = envelope.canonical_bytes
        receipt.signature = envelope.signature
        receipt.signing_key_id = envelope.key_id
        receipt.status = ReceiptStatus.SIGNED
        receipt.signed_at = timezone.now()
        receipt.attempts += 1
        receipt.last_error = ""
        receipt.save()

        # Tell the polling client the receipt is available.
        receipt.event.operations.update(receipt_ready=True)
        return True


def _outcome_for_event(event) -> str:
    from apps.verification.models import VerificationEventType, VerificationOutcome

    return {
        VerificationEventType.FIRST_REDEMPTION: VerificationOutcome.VERIFIED_FIRST,
        VerificationEventType.REPEAT_CHECK: VerificationOutcome.PREVIOUSLY_VERIFIED,
        VerificationEventType.PREACTIVATION_ATTEMPT: VerificationOutcome.NOT_ACTIVATED,
    }.get(event.event_type, VerificationOutcome.RESTRICTED)


@shared_task(name="verification.sign_pending_receipts")
def sign_pending_receipts(limit: int = 100) -> dict:
    """Drain the outbox. Scheduled periodically and safe to run concurrently."""
    pending = (
        SignedReceipt.objects.filter(status=ReceiptStatus.PENDING)
        .order_by("created_at")
        .values_list("id", flat=True)[:limit]
    )
    signed = 0
    failed = 0
    for receipt_id in list(pending):
        if sign_one_receipt(receipt_id):
            signed += 1
        else:
            failed += 1
    return {"signed": signed, "failed": failed}
