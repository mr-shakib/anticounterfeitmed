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


@transaction.atomic
def record_completion(
    *,
    unit: PackageUnit,
    step: str,
    completed_at: datetime,
    recorded_by,
    source_reference: str,
    reason: str = "",
) -> ManufacturingCompletionEvent:
    """Record one completed manufacturing step for one unit.

    A QC rejection voids the unit instead of advancing it.
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
            # Recorded so no reader can mistake this for factory scan evidence.
            "manufacturer_asserted": True,
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
