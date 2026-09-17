"""Recording manufacturer-asserted manufacturing steps.

The response deliberately echoes that these are assertions rather than captured
factory evidence, because the portal must not present them as scan data.
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.organizations.permissions import STAFF_AUTH, IsManufacturerStaff, owns
from apps.qc.models import ManufacturingStep
from apps.qc.services import StepOutOfOrder, activation_prerequisites_met, record_completion
from apps.serialization.models import PackageUnit


class ConfirmationSerializer(serializers.Serializer):
    unit_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=5000
    )
    step = serializers.ChoiceField(choices=[c[0] for c in ManufacturingStep.choices])
    completed_at = serializers.DateTimeField()
    source_reference = serializers.CharField(max_length=300)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def manufacturing_confirmations(request):
    serializer = ConfirmationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    units = list(
        PackageUnit.objects.select_related("batch__product__manufacturer").filter(
            pk__in=data["unit_ids"]
        )
    )
    found = {str(u.id) for u in units}
    missing = [str(uid) for uid in data["unit_ids"] if str(uid) not in found]

    # Any unit belonging to someone else makes the whole call a not-found,
    # rather than silently recording the subset the caller happens to own.
    foreign = [u for u in units if not owns(request.membership, u.batch.product.manufacturer)]
    if foreign or missing:
        return Response(
            {
                "code": "NOT_FOUND",
                "detail": "One or more units do not exist for this manufacturer.",
                "missing_count": len(missing) + len(foreign),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    recorded, rejected = [], []
    for unit in units:
        try:
            record_completion(
                unit=unit,
                step=data["step"],
                completed_at=data["completed_at"],
                recorded_by=request.user,
                source_reference=data["source_reference"],
                reason=data.get("reason", ""),
            )
            recorded.append(str(unit.id))
        except (StepOutOfOrder, ValueError) as exc:
            rejected.append({"unit_id": str(unit.id), "reason": str(exc)})

    return Response(
        {
            "recorded": len(recorded),
            "rejected": rejected,
            "evidence_source": "manufacturer-asserted",
            "notice": (
                "Recorded from an operational document supplied by manufacturer "
                "staff. This is not automatically captured factory scan evidence."
            ),
        },
        status=status.HTTP_200_OK if recorded else status.HTTP_409_CONFLICT,
    )


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def unit_readiness(request, unit_id):
    """Report whether a unit has everything activation requires, and what is missing."""
    unit = (
        PackageUnit.objects.select_related("batch__product__manufacturer")
        .filter(pk=unit_id)
        .first()
    )
    if unit is None or not owns(request.membership, unit.batch.product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such unit."},
            status=status.HTTP_404_NOT_FOUND,
        )
    ready, missing = activation_prerequisites_met(unit)
    return Response(
        {
            "unit_id": str(unit.id),
            "lifecycle": unit.lifecycle,
            "activation_ready": ready,
            "missing_steps": missing,
        }
    )
