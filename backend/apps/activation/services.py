"""Activation: the only point where a manufacturer key signs.

A unit becomes ACTIVE and its credential becomes available in the same
transaction, so a unit can never be active without a valid credential. A bulk
run reports per-unit results honestly: a batch with failures is never described
as fully activated, and retries cover only the units that failed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from apps.activation.models import (
    ActivationCredential,
    ActivationJob,
    ActivationJobItem,
    ActivationJobStatus,
)
from apps.audit.models import AuditAction, AuditEvent
from apps.catalog.models import Batch
from apps.organizations.models import StaffMembership
from apps.qc.services import activation_prerequisites_met
from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.trust.models import KeyPurpose
from apps.trust.services import active_key_for
from apps.trust.signing import SignerUnavailable, get_signer
from medcrypto import canonicalise
from medcrypto.contexts import Context
from medcrypto.records import ProductSnapshot, build_activation_record, credential_digest


class ActivationNotPermitted(Exception):
    """The actor or the batch is not eligible to activate."""


@dataclass
class ActivationOutcome:
    job: ActivationJob
    succeeded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def fully_succeeded(self) -> bool:
        return bool(self.succeeded) and not self.failed


def _eligibility_failure(unit: PackageUnit, batch: Batch) -> str | None:
    """Return why a unit cannot be activated, or None if it can."""
    if unit.lifecycle != UnitLifecycle.COVERED:
        return f"unit is {unit.lifecycle}, expected COVERED"
    if unit.is_blocked:
        return "unit is blocked"
    if batch.is_recalled:
        return "batch is recalled"
    if batch.expires_on <= timezone.now().date():
        return "batch expiry has passed"
    ready, missing = activation_prerequisites_met(unit)
    if not ready:
        return f"missing manufacturing records: {', '.join(missing) or 'lifecycle'}"
    return None


@transaction.atomic
def _activate_one(
    *,
    unit: PackageUnit,
    batch: Batch,
    job: ActivationJob,
    key,
    signer,
) -> None:
    """Sign and activate a single unit, or raise.

    Runs in its own transaction so one unit's failure cannot roll back the
    units that already succeeded in a bulk run.
    """
    locked = PackageUnit.objects.select_for_update().get(pk=unit.pk)
    failure = _eligibility_failure(locked, batch)
    if failure:
        raise ActivationNotPermitted(failure)

    product = batch.product
    activated_at = timezone.now()

    qc_event = locked.manufacturing_events.filter(step="QC_PASSED").first()
    coat_event = locked.manufacturing_events.filter(step="COATED").first()

    record = build_activation_record(
        key_id=key.key_id,
        manufacturer_id=str(product.manufacturer_id),
        package_id=str(locked.id),
        token_sha256=bytes(locked.token_sha256),
        product=ProductSnapshot(
            brand=product.brand,
            generic=product.generic,
            strength=product.strength,
            dosage_form=product.dosage_form,
            pack_description=product.pack_description,
        ),
        batch_number=batch.batch_number,
        manufactured_on=batch.manufactured_on,
        expires_on=batch.expires_on,
        qc_event_id=str(qc_event.id) if qc_event else "",
        coating_event_id=str(coat_event.id) if coat_event else "",
        activation_approval_id=job.approval_id,
        activated_at=activated_at,
        record_version=locked.version,
    )
    payload = canonicalise(record)

    signature = signer.sign(
        key_id=key.key_id,
        context=Context.ACTIVATION.value.decode(),
        payload=payload,
    )

    ActivationCredential.objects.create(
        unit=locked,
        job=job,
        canonical_bytes=payload,
        signature=signature,
        signing_key=key,
        credential_digest=credential_digest(payload),
        snapshot_version=locked.version,
        activated_at=activated_at,
    )

    # The credential exists before the unit is published as active, and both
    # land in the same transaction.
    locked.lifecycle = UnitLifecycle.ACTIVE
    locked.activated_at = activated_at
    locked.save(update_fields=["lifecycle", "activated_at"])

    AuditEvent.objects.create(
        action=AuditAction.UNIT_ACTIVATED,
        organization=product.manufacturer,
        unit_id=locked.id,
        batch_id=batch.id,
        detail={
            "approval_id": job.approval_id,
            "key_id": key.key_id,
            "credential_digest": credential_digest(payload),
        },
    )


def activate_units(
    *,
    batch: Batch,
    units: list[PackageUnit],
    membership: StaffMembership,
    approval_id: str | None = None,
) -> ActivationOutcome:
    """Approve, sign and activate the eligible units in ``units``.

    Only a release manager of the owning organization may call this, and the
    check is on the membership rather than on anything the caller passes in.
    """
    if not membership.may_activate:
        raise ActivationNotPermitted(
            "activation requires an enabled release manager of an approved, "
            "unsuspended manufacturer"
        )
    if membership.organization_id != batch.product.manufacturer_id:
        raise ActivationNotPermitted("cannot activate another manufacturer's units")

    key = active_key_for(purpose=KeyPurpose.ACTIVATION, organization=batch.product.manufacturer)
    signer = get_signer()

    job = ActivationJob.objects.create(
        organization=batch.product.manufacturer,
        batch=batch,
        approved_by=membership.user,
        approval_id=approval_id or f"appr-{uuid.uuid4()}",
        status=ActivationJobStatus.RUNNING,
        requested_count=len(units),
    )

    outcome = ActivationOutcome(job=job)

    for unit in units:
        try:
            _activate_one(unit=unit, batch=batch, job=job, key=key, signer=signer)
        except Exception as exc:  # noqa: BLE001
            # One unit's failure must not abandon the rest of the run, so every
            # failure is captured per unit and reported rather than raised.
            reason = str(exc) or exc.__class__.__name__
            ActivationJobItem.objects.create(
                job=job, unit=unit, succeeded=False, failure_reason=reason,
                processed_at=timezone.now(),
            )
            outcome.failed.append((str(unit.id), reason))
        else:
            ActivationJobItem.objects.create(
                job=job, unit=unit, succeeded=True, processed_at=timezone.now()
            )
            outcome.succeeded.append(str(unit.id))

    job.succeeded_count = len(outcome.succeeded)
    job.failed_count = len(outcome.failed)
    job.status = (
        ActivationJobStatus.COMPLETED
        if outcome.fully_succeeded
        else ActivationJobStatus.COMPLETED_WITH_FAILURES
        if outcome.succeeded
        else ActivationJobStatus.FAILED
    )
    job.finished_at = timezone.now()
    job.save(update_fields=["succeeded_count", "failed_count", "status", "finished_at"])
    return outcome


def retry_failed(*, job: ActivationJob, membership: StaffMembership) -> ActivationOutcome:
    """Re-attempt only the units that failed in ``job``."""
    failed_units = [
        item.unit for item in job.items.select_related("unit").filter(succeeded=False)
    ]
    return activate_units(
        batch=job.batch, units=failed_units, membership=membership
    )
