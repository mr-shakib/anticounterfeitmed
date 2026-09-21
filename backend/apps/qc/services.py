"""Recording manufacturer-asserted manufacturing completion.

These are operational assertions typed in by manufacturer staff, not captured
factory scan evidence. Every record therefore carries who entered it, when the
step actually finished, when it was typed, and which operational document it
came from -- and the steps must be recorded in order, so a unit cannot reach
activation without the prerequisites behind it.
"""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.db.models import Count, Q

from medcrypto import hash_token, is_well_formed_token

from apps.audit.models import AuditAction, AuditEvent
from apps.qc.models import ManufacturingCompletionEvent, ManufacturingStep
from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.serialization.services import void_unit

#: Which lifecycle state each successful step moves a unit into.
STEP_TRANSITIONS: dict[str, str] = {
    ManufacturingStep.PRINTED: UnitLifecycle.PRINTED,
    ManufacturingStep.QC_PASSED: UnitLifecycle.QC_PASSED,
    ManufacturingStep.COATED: UnitLifecycle.COVERED,
}


class StepOutOfOrder(Exception):
    """The unit is not in the state this step follows."""


class ScanNotMatched(Exception):
    """The scanned code is not a unit of this batch.

    Deliberately says nothing about whether it is a code at all. An endpoint
    that accepts raw tokens must not become an oracle for guessing them.
    """


class ScanNotApplicable(Exception):
    """The unit exists, but a print scan cannot be recorded against it."""


@transaction.atomic
def record_completion(
    *,
    unit: PackageUnit,
    step: str,
    completed_at: datetime,
    recorded_by,
    source_reference: str,
    reason: str = "",
    is_manufacturer_asserted: bool = True,
) -> ManufacturingCompletionEvent:
    """Record one completed manufacturing step for one unit.

    A QC rejection voids the unit instead of advancing it.

    ``is_manufacturer_asserted`` is true for anything a person typed in, and
    false only where this system observed the step itself -- today, a printed
    code read back by :func:`record_print_scan`. Reports and the portal show
    the difference, because the two are not equally good evidence.
    """
    if completed_at.tzinfo is None:
        raise ValueError("completed_at must be timezone-aware")
    if not source_reference:
        raise ValueError("a source record reference is required")

    if step == ManufacturingStep.QC_REJECTED:
        event = ManufacturingCompletionEvent.objects.create(
            unit=unit,
            step=step,
            completed_at=completed_at,
            recorded_by=recorded_by,
            source_reference=source_reference,
            reason=reason,
            is_manufacturer_asserted=is_manufacturer_asserted,
        )
        void_unit(
            unit=unit,
            reason=reason or "QC rejected",
            actor_description=str(recorded_by),
        )
        return event

    target = STEP_TRANSITIONS.get(step)
    if target is None:
        raise ValueError(f"unknown step {step}")
    if not unit.can_transition_to(target):
        raise StepOutOfOrder(
            f"unit is {unit.lifecycle}; {step} cannot be recorded from that state"
        )

    event = ManufacturingCompletionEvent.objects.create(
        unit=unit,
        step=step,
        completed_at=completed_at,
        recorded_by=recorded_by,
        source_reference=source_reference,
        reason=reason,
        is_manufacturer_asserted=is_manufacturer_asserted,
    )

    unit.lifecycle = target
    unit.save(update_fields=["lifecycle"])

    AuditEvent.objects.create(
        action=AuditAction.MANUFACTURING_RECORDED,
        organization=unit.batch.product.manufacturer,
        actor_user=recorded_by if getattr(recorded_by, "pk", None) else None,
        unit_id=unit.id,
        batch_id=unit.batch_id,
        detail={
            "step": step,
            "completed_at": completed_at.isoformat(),
            "source_reference": source_reference,
            # Recorded so no reader can mistake an assertion for scan evidence.
            "manufacturer_asserted": is_manufacturer_asserted,
        },
    )
    return event


def activation_prerequisites_met(unit: PackageUnit) -> tuple[bool, list[str]]:
    """Report whether a unit has every record activation requires.

    Returns the verdict and the list of missing steps, so the portal can explain
    a refusal rather than simply disabling a button.
    """
    required = {
        ManufacturingStep.PRINTED,
        ManufacturingStep.QC_PASSED,
        ManufacturingStep.COATED,
    }
    present = set(
        ManufacturingCompletionEvent.objects.filter(unit=unit, step__in=required).values_list(
            "step", flat=True
        )
    )
    missing = sorted(required - present)
    return (not missing and unit.lifecycle == UnitLifecycle.COVERED), missing


@transaction.atomic
def record_print_scan(*, batch, token: str, recorded_by, scanned_at: datetime) -> dict:
    """Record that a printed code was read back and matched, on the print line.

    This is the one manufacturing record this system observes for itself, so it
    is stored with ``is_manufacturer_asserted=False``. What it proves is narrow
    and worth stating: the printed symbol decodes, and it decodes to a unit of
    this batch. It says nothing about QC or about the scratch coating -- the
    coating is applied *after* scanning and covers the code, so no scan can
    ever evidence it.

    The raw token lives in this function's arguments and nowhere else. Only its
    digest is compared, and neither the event, the audit record nor the
    response carries it.

    Scanning the same unit twice is not an error. The line will re-read a
    label, and refusing would push someone into working around the system.
    """
    if not is_well_formed_token(token):
        raise ScanNotMatched("not one of this batch's codes")

    unit = (
        PackageUnit.objects.select_for_update()
        .filter(batch=batch, token_sha256=hash_token(token))
        .first()
    )
    if unit is None:
        raise ScanNotMatched("not one of this batch's codes")

    existing = unit.manufacturing_events.filter(step=ManufacturingStep.PRINTED).first()
    if existing is not None:
        # Whether printing was scanned or signed off by hand is exactly what
        # the person holding the label needs to know, so say which.
        return {
            "unit": unit,
            "already_scanned": True,
            "previously_scanned": not existing.is_manufacturer_asserted,
        }

    if unit.is_blocked:
        raise ScanNotApplicable("unit is blocked")
    if unit.lifecycle != UnitLifecycle.CREATED:
        # Includes voided and already-activated units. A scan is a print-line
        # record; accepting one afterwards would let the endpoint confirm the
        # tokens of medicine already in circulation.
        raise ScanNotApplicable(f"unit is {unit.lifecycle}, expected CREATED")

    record_completion(
        unit=unit,
        step=ManufacturingStep.PRINTED,
        completed_at=scanned_at,
        recorded_by=recorded_by,
        source_reference=f"print-line scan {scanned_at.date().isoformat()}",
        is_manufacturer_asserted=False,
    )
    return {"unit": unit, "already_scanned": False, "previously_scanned": False}


def batch_manufacturing_progress(batch_id) -> dict:
    """How far a batch has got through the manufacturing records.

    Activation needs printing, QC and coating recorded against each unit, and
    until now the portal could only offer the button and report afterwards how
    many units it skipped. This is the same question asked beforehand.

    Counts are of *units*, not events: QC rejection may be recorded more than
    once for a unit, the other steps at most once.

    ``units_ready`` is the per-unit view only. A recalled or expired batch
    activates nothing regardless of what its units have recorded.

    ``units_scan_verified`` is the subset this system observed itself, by
    reading the printed code back on the line. The rest were typed in.
    """
    counts = {step: 0 for step in ManufacturingStep.values}
    tallied = (
        ManufacturingCompletionEvent.objects.filter(unit__batch_id=batch_id)
        .values("step")
        .annotate(units=Count("unit_id", distinct=True))
    )
    for row in tallied:
        counts[row["step"]] = row["units"]

    required = [
        ManufacturingStep.PRINTED,
        ManufacturingStep.QC_PASSED,
        ManufacturingStep.COATED,
    ]
    units_ready = (
        PackageUnit.objects.filter(
            batch_id=batch_id,
            lifecycle=UnitLifecycle.COVERED,
            is_blocked=False,
        )
        .annotate(
            steps_present=Count(
                "manufacturing_events",
                filter=Q(manufacturing_events__step__in=required),
                distinct=True,
            )
        )
        .filter(steps_present=len(required))
        .count()
    )

    scan_verified = (
        ManufacturingCompletionEvent.objects.filter(
            unit__batch_id=batch_id,
            step=ManufacturingStep.PRINTED,
            is_manufacturer_asserted=False,
        )
        .values("unit_id")
        .distinct()
        .count()
    )

    return {
        "counts_by_step": counts,
        "units_ready": units_ready,
        "units_scan_verified": scan_verified,
    }
