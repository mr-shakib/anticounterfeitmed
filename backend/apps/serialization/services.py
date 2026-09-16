"""Serial and token generation.

Raw tokens exist here and nowhere else. ``create_print_job`` returns them to its
caller exactly once, for the controlled label export, and the database keeps
only their digests. Nothing in this module logs a token, and no later query can
recover one.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction, AuditEvent
from apps.catalog.models import Batch
from apps.organizations.models import Organization
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

    job.issued_count = count
    job.save(update_fields=["issued_count"])

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
