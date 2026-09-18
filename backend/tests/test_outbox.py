"""The receipt outbox and post-commit failure recovery (docs/08, docs/11)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.serialization.models import UnitLifecycle
from apps.verification.models import (
    ReceiptStatus,
    SignedReceipt,
    VerificationEvent,
    VerificationEventType,
)
from apps.verification.tasks import sign_one_receipt, sign_pending_receipts
from medcrypto.contexts import Context
from medcrypto.signing import verify
from tests.test_api import (  # noqa: F401
    ATTEST,
    active_package,
    auth,
    client,
    make_session,
    platform_keys,
    _allow_insecure_attestation,
)
from tests.test_end_to_end import factory, take_through_manufacturing  # noqa: F401


def confirm_once(client, credential, token):
    prepared = client.post(
        reverse("consumer-prepare"), {"token": token, "nonce": "n"},
        format="json", **auth(credential),
    ).data
    return client.post(
        reverse("consumer-confirm"),
        {
            "unit_id": prepared["unit_id"],
            "challenge_id": prepared["challenge_id"],
            "idempotency_key": "outbox-1",
            "nonce": "n2",
        },
        format="json",
        **auth(credential),
    ).data


@pytest.mark.django_db(transaction=True)
def test_receipt_is_queued_then_signed(client, active_package):
    _org, unit, token = active_package
    credential = make_session(client)
    confirm_once(client, credential, token)

    receipt = SignedReceipt.objects.get(event__unit=unit)
    assert receipt.status == ReceiptStatus.PENDING

    result = sign_pending_receipts()
    assert result == {"signed": 1, "failed": 0}

    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.SIGNED

    from apps.trust.models import KeyPurpose
    from apps.trust.services import active_key_for

    key = active_key_for(purpose=KeyPurpose.STATUS)
    verify(
        bytes(key.public_key),
        Context.STATUS,
        bytes(receipt.canonical_bytes),
        bytes(receipt.signature),
    )


@pytest.mark.django_db(transaction=True)
def test_signer_failure_after_commit_never_undoes_the_redemption(
    client, active_package, monkeypatch
):
    """The acceptance gate: stop the signer after commit, lose nothing."""
    _org, unit, token = active_package
    credential = make_session(client)
    confirmed = confirm_once(client, credential, token)

    # The redemption is already durable at this point.
    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.REDEEMED
    event_id = VerificationEvent.objects.get(
        unit=unit, event_type=VerificationEventType.FIRST_REDEMPTION
    ).id

    receipt = SignedReceipt.objects.get(event__unit=unit)

    # The signer is down.
    def broken(**kwargs):
        raise RuntimeError("signer unavailable")

    monkeypatch.setattr("apps.verification.envelopes.sign_status", broken)
    assert sign_one_receipt(receipt.id) is False

    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.PENDING, "must stay pending for retry"
    assert receipt.attempts == 1
    assert "signer unavailable" in receipt.last_error

    # The redemption is untouched, and no duplicate event appeared.
    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.REDEEMED
    assert VerificationEvent.objects.filter(unit=unit).count() == 1

    # The client polls and gets the same event back.
    url = reverse("consumer-operation-status", args=[confirmed["operation_id"]])
    polled = client.post(url, {"nonce": "n3"}, format="json", **auth(credential))
    assert polled.status_code == 200
    assert polled.data["receipt_ready"] is False

    # The signer recovers; the same event is signed, with no new event.
    monkeypatch.undo()
    assert sign_one_receipt(receipt.id) is True

    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.SIGNED
    assert receipt.event_id == event_id
    assert VerificationEvent.objects.filter(unit=unit).count() == 1

    polled = client.post(url, {"nonce": "n4"}, format="json", **auth(credential))
    assert polled.data["receipt_ready"] is True


@pytest.mark.django_db(transaction=True)
def test_signing_is_idempotent(client, active_package):
    """A duplicated or retried job must not re-sign."""
    _org, unit, token = active_package
    credential = make_session(client)
    confirm_once(client, credential, token)

    receipt = SignedReceipt.objects.get(event__unit=unit)
    assert sign_one_receipt(receipt.id) is True
    receipt.refresh_from_db()
    first_signature = bytes(receipt.signature)
    first_signed_at = receipt.signed_at

    assert sign_one_receipt(receipt.id) is True
    receipt.refresh_from_db()
    assert bytes(receipt.signature) == first_signature
    assert receipt.signed_at == first_signed_at

    assert sign_pending_receipts() == {"signed": 0, "failed": 0}


@pytest.mark.django_db(transaction=True)
def test_receipt_gives_up_after_repeated_failures(client, active_package, monkeypatch):
    _org, unit, token = active_package
    credential = make_session(client)
    confirm_once(client, credential, token)
    receipt = SignedReceipt.objects.get(event__unit=unit)

    monkeypatch.setattr(
        "apps.verification.envelopes.sign_status",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("down")),
    )
    from apps.verification.tasks import MAX_ATTEMPTS

    for _ in range(MAX_ATTEMPTS):
        sign_one_receipt(receipt.id)

    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.FAILED
    # Even after giving up on the receipt, the redemption stands.
    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.REDEEMED


@pytest.mark.django_db(transaction=True)
def test_confirm_tells_the_app_the_receipt_is_not_ready_yet(client, active_package):
    """The event is committed; the receipt is not. The app must be able to tell.

    Without this the app would either claim a receipt it does not have, or
    imply the verification failed when it plainly succeeded.
    """
    _org, unit, token = active_package
    credential = make_session(client)
    confirmed = confirm_once(client, credential, token)

    assert confirmed["first_verification_recorded"] is True
    assert confirmed["receipt_ready"] is False

    sign_pending_receipts()

    url = reverse("consumer-operation-status", args=[confirmed["operation_id"]])
    polled = client.post(url, {"nonce": "n"}, format="json", **auth(credential))
    assert polled.data["receipt_ready"] is True
