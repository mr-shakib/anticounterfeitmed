"""Serial and token generation.

Raw tokens exist here and nowhere else. ``create_print_job`` returns them to its
caller exactly once, for the controlled label export, and the database keeps
only their digests. Nothing in this module logs a token, and no later query can
recover one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.catalog.models import Batch
from apps.organizations.models import Organization
from apps.serialization.export_store import encrypt_export
from apps.serialization.models import PackageUnit, PrintJob, PrintJobStatus, UnitLifecycle
from medcrypto import generate_token, hash_token


class IssuanceNotPermitted(Exception):
    """The organization may not issue units."""


@dataclass(frozen=True)
class IssuedUnit:
    """One generated unit, paired with its raw token for the label export.

    This object is transient. It must reach the export and then be dropped; it
    must never be stored, logged or serialised into a response.
    """

    unit_id: str
    external_reference: str
    token: str


@dataclass(frozen=True)
class PrintJobResult:
    print_job: PrintJob
    units: list[IssuedUnit]


def external_reference_for(batch: Batch, index: int) -> str:
    """Human-readable reference printed beside the QR.

    It identifies a unit for reconciliation and support conversations. It is
    deliberately guessable and can never redeem anything.
    """
    return f"{batch.batch_number}-{index:06d}"


@transaction.atomic
def create_print_job(
    *,
    batch: Batch,
    count: int,
    created_by: str = "",
) -> PrintJobResult:
    """Generate ``count`` units for ``batch``, one per strip.

    One strip carries exactly one QR, so a 1,000-strip run produces 1,000 units
    and 1,000 distinct tokens.
    """
    if count < 1:
        raise ValueError("count must be positive")

    manufacturer: Organization = batch.product.manufacturer
    if not manufacturer.can_issue:
        raise IssuanceNotPermitted(
            f"{manufacturer.name} is not an approved, unsuspended manufacturer"
        )
    if batch.is_recalled:
        raise IssuanceNotPermitted("cannot issue units for a recalled batch")

    job = PrintJob.objects.create(
        manufacturer=manufacturer,
        batch=batch,
        planned_count=count,
        status=PrintJobStatus.GENERATED,
        created_by=created_by,
    )

    existing = PackageUnit.objects.filter(batch=batch).count()
    issued: list[IssuedUnit] = []
    units: list[PackageUnit] = []

    for offset in range(count):
        token = generate_token()
        reference = external_reference_for(batch, existing + offset + 1)
        unit = PackageUnit(
            batch=batch,
            print_job=job,
            external_reference=reference,
            token_sha256=hash_token(token),
            lifecycle=UnitLifecycle.CREATED,
        )
        units.append(unit)
        issued.append(
            IssuedUnit(unit_id=str(unit.id), external_reference=reference, token=token)
        )

    PackageUnit.objects.bulk_create(units)

    # Retain the export, encrypted and on a clock, so the labels can be
    # collected again before the job is reconciled. Without this a manufacturer
    # who navigates away loses a run's worth of codes and has to void and
    # reissue every unit.
    from django.conf import settings

    job.export_ciphertext = encrypt_export(
        [
            {"external_reference": u.external_reference, "token": u.token}
            for u in issued
        ]
    )
    job.export_expires_at = timezone.now() + timedelta(
        days=settings.EXPORT_MAX_AGE_DAYS
    )
    job.issued_count = count
    job.save(
        update_fields=["issued_count", "export_ciphertext", "export_expires_at"]
    )

    AuditEvent.objects.create(
        action=AuditAction.UNITS_GENERATED,
        organization=manufacturer,
        batch_id=batch.id,
        actor_description=created_by,
        # Counts only. A token, or anything derived from one, must never
        # reach an audit record.
        detail={"print_job_id": str(job.id), "count": count},
    )

    return PrintJobResult(print_job=job, units=issued)


@transaction.atomic
def reconcile_print_job(
    *,
    job: PrintJob,
    printed: int,
    rejected: int,
    actor_description: str = "",
) -> PrintJob:
    """Record the counts that came back from printing.

    Reconciliation starts the clock on the export: once quantities are agreed
    there is no further reason to hold raw tokens, so it is deleted within the
    grace period rather than at the longer ceiling.
    """
    from django.conf import settings

    job.reconciled_printed = printed
    job.reconciled_rejected = rejected
    job.reconciled_at = timezone.now()
    job.status = PrintJobStatus.RECONCILED
    job.export_expires_at = timezone.now() + timedelta(
        hours=settings.EXPORT_GRACE_HOURS_AFTER_RECONCILE
    )
    job.save(
        update_fields=[
            "reconciled_printed", "reconciled_rejected", "reconciled_at",
            "status", "export_expires_at",
        ]
    )

    AuditEvent.objects.create(
        action=AuditAction.UNITS_GENERATED,
        organization=job.manufacturer,
        batch_id=job.batch_id,
        actor_description=actor_description,
        reason="print job reconciled",
        detail={
            "print_job_id": str(job.id),
            "printed": printed,
            "rejected": rejected,
            "export_expires_at": job.export_expires_at.isoformat(),
        },
    )
    return job


def purge_expired_exports(now=None) -> int:
    """Delete label exports that have passed their expiry.

    Run on a schedule. Deletion is recorded on the job so the disposal of an
    artifact containing raw tokens is visible rather than silent.
    """
    now = now or timezone.now()
    expired = PrintJob.objects.filter(
        export_ciphertext__isnull=False,
        export_expires_at__lt=now,
        export_deleted_at__isnull=True,
    )
    count = 0
    for job in expired:
        job.export_ciphertext = None
        job.export_deleted_at = now
        job.save(update_fields=["export_ciphertext", "export_deleted_at"])
        count += 1
    return count


@transaction.atomic
def void_unit(*, unit: PackageUnit, reason: str, actor_description: str = "") -> PackageUnit:
    """Void a unit so it can never be activated.

    Used for QC rejections and damage. Replacements get freshly generated
    tokens; a voided unit's token is never reissued.
    """
    if not unit.can_transition_to(UnitLifecycle.VOID):
        raise ValueError(f"cannot void a unit in state {unit.lifecycle}")

    unit.lifecycle = UnitLifecycle.VOID
    unit.void_reason = reason
    unit.voided_at = timezone.now()
    unit.save(update_fields=["lifecycle", "void_reason", "voided_at"])

    AuditEvent.objects.create(
        action=AuditAction.UNIT_VOIDED,
        organization=unit.batch.product.manufacturer,
        unit_id=unit.id,
        batch_id=unit.batch_id,
        actor_description=actor_description,
        reason=reason,
    )
    return unit
