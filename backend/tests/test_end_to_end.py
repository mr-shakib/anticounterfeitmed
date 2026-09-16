"""The full chain: generate, record manufacturing, activate, preview, confirm.

The client-side assertions here deliberately mirror what the Flutter app must
do -- verify the signature on the received bytes, check the token commitment,
check the credential belongs to this unit -- so that this test fails if the
server ever produces something the app would reject.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.activation.services import ActivationNotPermitted, activate_units, retry_failed
from apps.catalog.models import Batch, Product
from apps.organizations.models import (
    ApprovalStatus,
    Organization,
    OrganizationType,
    StaffMembership,
    StaffRole,
)
from apps.qc.models import ManufacturingStep
from apps.qc.services import StepOutOfOrder, record_completion
from apps.serialization.models import UnitLifecycle
from apps.serialization.services import IssuanceNotPermitted, create_print_job
from apps.trust.models import KeyPurpose
from apps.trust.services import provision_signing_key, publish_trust_manifest
from apps.verification.models import VerificationOutcome
from apps.verification.services import confirm_verification, prepare_verification
from medcrypto.contexts import Context
from medcrypto.records import check_activation_binding
from medcrypto.signing import verify
from medcrypto.tokens import hash_token
from tests.conftest import make_session_and_challenge

User = get_user_model()


@pytest.fixture
def factory(db):
    """A manufacturer with an approved key and a release manager."""

    def build(name="Test Pharmaceuticals Ltd"):
        org = Organization.objects.create(
            type=OrganizationType.MANUFACTURER,
            name=name,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=timezone.now(),
        )
        user = User.objects.create_user(
            username=f"release-{org.id}", password="x" * 16
        )
        membership = StaffMembership.objects.create(
            user=user, organization=org, role=StaffRole.RELEASE_MANAGER, mfa_enabled=True
        )
        product = Product.objects.create(
            manufacturer=org,
            brand="Napa",
            generic="Paracetamol",
            strength="500 mg",
            dosage_form="Tablet",
            pack_description="Strip of 10 tablets",
        )
        batch = Batch.objects.create(
            product=product,
            batch_number=f"BN-{org.id.hex[:6]}",
            manufactured_on=date.today() - timedelta(days=30),
            expires_on=date.today() + timedelta(days=365),
            planned_unit_count=10,
        )
        provision_signing_key(purpose=KeyPurpose.ACTIVATION, organization=org)
        return org, membership, batch

    return build


def take_through_manufacturing(units, user):
    """Record printed, QC passed and coated for every unit."""
    now = timezone.now()
    for issued in units:
        from apps.serialization.models import PackageUnit

        unit = PackageUnit.objects.get(pk=issued.unit_id)
        for step in (
            ManufacturingStep.PRINTED,
            ManufacturingStep.QC_PASSED,
            ManufacturingStep.COATED,
        ):
            record_completion(
                unit=unit,
                step=step,
                completed_at=now,
                recorded_by=user,
                source_reference="production-log-2026-09-17",
            )


@pytest.mark.django_db(transaction=True)
def test_full_happy_path(factory, settings):
    org, membership, batch = factory()

    # 1. Serialise: one QR per strip.
    result = create_print_job(batch=batch, count=5, created_by="operator")
    assert len(result.units) == 5
    assert len({u.token for u in result.units}) == 5

    # 2. Record the off-system manufacturing steps.
    take_through_manufacturing(result.units, membership.user)

    # 3. Activate.
    from apps.serialization.models import PackageUnit

    units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]
    outcome = activate_units(batch=batch, units=units, membership=membership)
    assert outcome.fully_succeeded, outcome.failed
    assert outcome.job.succeeded_count == 5

    for unit in units:
        unit.refresh_from_db()
        assert unit.lifecycle == UnitLifecycle.ACTIVE
        assert unit.activation_credential is not None

    # 4. Preview, verifying exactly as the app must.
    target = result.units[0]
    session, _ = make_session_and_challenge(units[0])
    prepared = prepare_verification(session=session, token=target.token)

    assert prepared.outcome == VerificationOutcome.VERIFIED_FIRST
    assert prepared.challenge is not None

    key = units[0].activation_credential.signing_key
    verify(
        bytes(key.public_key),
        Context.ACTIVATION,
        prepared.credential_bytes,
        prepared.credential_signature,
    )
    record = check_activation_binding(
        prepared.credential_bytes,
        expected_token_sha256=hash_token(target.token),
        expected_manufacturer_id=str(org.id),
        expected_key_id=key.key_id,
    )
    assert record["product_snapshot"]["brand"] == "Napa"
    assert record["batch_number"] == batch.batch_number

    # Previewing must not redeem.
    units[0].refresh_from_db()
    assert units[0].lifecycle == UnitLifecycle.ACTIVE

    # 5. Confirm.
    confirmed = confirm_verification(
        session=session,
        unit_id=units[0].id,
        challenge_id=prepared.challenge.id,
        idempotency_key="e2e-key",
        body={"unit": str(units[0].id)},
    )
    assert confirmed.outcome == VerificationOutcome.VERIFIED_FIRST
    assert confirmed.first_redemption

    units[0].refresh_from_db()
    assert units[0].lifecycle == UnitLifecycle.REDEEMED

    # A receipt is queued in the same transaction as the event.
    assert confirmed.event.receipt.status == "PENDING"

    # 6. A second scan is a repeat, not a second redemption.
    session2, _ = make_session_and_challenge(units[0])
    again = prepare_verification(session=session2, token=target.token)
    assert again.outcome == VerificationOutcome.PREVIOUSLY_VERIFIED


@pytest.mark.django_db(transaction=True)
def test_credential_from_another_unit_fails_binding(factory):
    """The QR binding acceptance test, end to end with real signatures."""
    org, membership, batch = factory()
    result = create_print_job(batch=batch, count=2)
    take_through_manufacturing(result.units, membership.user)

    from apps.serialization.models import PackageUnit

    units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]
    activate_units(batch=batch, units=units, membership=membership)

    first, second = units[0], units[1]
    other_credential = second.activation_credential

    # The signature is genuine; the binding is wrong.
    verify(
        bytes(other_credential.signing_key.public_key),
        Context.ACTIVATION,
        bytes(other_credential.canonical_bytes),
        bytes(other_credential.signature),
    )
    from medcrypto.records import BindingError

    with pytest.raises(BindingError):
        check_activation_binding(
            bytes(other_credential.canonical_bytes),
            expected_token_sha256=hash_token(result.units[0].token),
            expected_manufacturer_id=str(org.id),
            expected_key_id=other_credential.signing_key.key_id,
        )


@pytest.mark.django_db(transaction=True)
def test_activation_requires_complete_manufacturing_records(factory):
    org, membership, batch = factory()
    result = create_print_job(batch=batch, count=3)

    from apps.serialization.models import PackageUnit

    units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]

    # Only the first unit gets the full set of records.
    take_through_manufacturing(result.units[:1], membership.user)
    # The second is printed but never QC'd or coated.
    record_completion(
        unit=units[1],
        step=ManufacturingStep.PRINTED,
        completed_at=timezone.now(),
        recorded_by=membership.user,
        source_reference="production-log",
    )

    outcome = activate_units(batch=batch, units=units, membership=membership)

    assert len(outcome.succeeded) == 1
    assert len(outcome.failed) == 2
    assert not outcome.fully_succeeded
    assert outcome.job.status == "COMPLETED_WITH_FAILURES"

    # A unit that failed signing must remain inactive and uncredentialed.
    units[1].refresh_from_db()
    assert units[1].lifecycle == UnitLifecycle.PRINTED
    assert not hasattr(units[1], "activation_credential") or (
        getattr(units[1], "activation_credential", None) is None
    )


@pytest.mark.django_db(transaction=True)
def test_steps_must_be_recorded_in_order(factory):
    org, membership, batch = factory()
    result = create_print_job(batch=batch, count=1)

    from apps.serialization.models import PackageUnit

    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)

    with pytest.raises(StepOutOfOrder):
        record_completion(
            unit=unit,
            step=ManufacturingStep.COATED,
            completed_at=timezone.now(),
            recorded_by=membership.user,
            source_reference="log",
        )


@pytest.mark.django_db(transaction=True)
def test_qc_rejection_voids_the_unit(factory):
    org, membership, batch = factory()
    result = create_print_job(batch=batch, count=1)

    from apps.serialization.models import PackageUnit

    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)
    record_completion(
        unit=unit,
        step=ManufacturingStep.PRINTED,
        completed_at=timezone.now(),
        recorded_by=membership.user,
        source_reference="log",
    )
    record_completion(
        unit=unit,
        step=ManufacturingStep.QC_REJECTED,
        completed_at=timezone.now(),
        recorded_by=membership.user,
        source_reference="log",
        reason="print defect",
    )

    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.VOID

    outcome = activate_units(batch=batch, units=[unit], membership=membership)
    assert not outcome.succeeded
    assert "VOID" in outcome.failed[0][1]


@pytest.mark.django_db(transaction=True)
def test_retry_reprocesses_only_failures(factory):
    org, membership, batch = factory()
    result = create_print_job(batch=batch, count=2)
    take_through_manufacturing(result.units[:1], membership.user)

    from apps.serialization.models import PackageUnit

    units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]
    first_run = activate_units(batch=batch, units=units, membership=membership)
    assert len(first_run.failed) == 1

    # Complete the records for the unit that failed, then retry.
    take_through_manufacturing(result.units[1:], membership.user)
    second_run = retry_failed(job=first_run.job, membership=membership)

    assert second_run.job.requested_count == 1, "retry must cover only the failures"
    assert len(second_run.succeeded) == 1
    units[1].refresh_from_db()
    assert units[1].lifecycle == UnitLifecycle.ACTIVE
