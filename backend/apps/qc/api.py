"""Recording manufacturer-asserted manufacturing steps.

The response deliberately echoes that these are assertions rather than captured
factory evidence, because the portal must not present them as scan data.
"""

from __future__ import annotations

from rest_framework import serializers, status
from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.response import Response

from apps.catalog.models import Batch
from apps.organizations.permissions import STAFF_AUTH, IsManufacturerStaff, owns
from apps.qc.models import ManufacturingStep
from apps.qc.services import (
    ScanNotApplicable,
    ScanNotMatched,
    StepOutOfOrder,
    activation_prerequisites_met,
    batch_manufacturing_progress,
    record_completion,
    record_print_scan,
)
from apps.qc.throttling import PrintScanThrottle
from apps.serialization.models import PackageUnit


class ConfirmationSerializer(serializers.Serializer):
    """Either a whole batch, or an explicit list of units.

    A batch is the ordinary case: a print run is recorded as one operation, and
    naming every unit would mean the caller had to hold the whole run in memory
    and page through it -- which is how a large batch ends up half recorded.
    """

    batch = serializers.UUIDField(required=False)
    unit_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, min_length=1, max_length=5000
    )
    step = serializers.ChoiceField(choices=[c[0] for c in ManufacturingStep.choices])
    completed_at = serializers.DateTimeField()
    source_reference = serializers.CharField(max_length=300)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("batch") and not attrs.get("unit_ids"):
            raise serializers.ValidationError("give either batch or unit_ids")
        return attrs


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def manufacturing_confirmations(request):
    serializer = ConfirmationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if data.get("batch"):
        batch = (
            Batch.objects.select_related("product__manufacturer")
            .filter(pk=data["batch"])
            .first()
        )
        if batch is None or not owns(request.membership, batch.product.manufacturer):
            return Response(
                {"code": "NOT_FOUND", "detail": "No such batch."},
                status=status.HTTP_404_NOT_FOUND,
            )
        queryset = PackageUnit.objects.select_related(
            "batch__product__manufacturer"
        ).filter(batch=batch)
        if data.get("unit_ids"):
            queryset = queryset.filter(pk__in=data["unit_ids"])
        units = list(queryset.order_by("external_reference"))
        if not units:
            return Response(
                {"code": "NO_UNITS", "detail": "No units matched."},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        units = list(
            PackageUnit.objects.select_related("batch__product__manufacturer").filter(
                pk__in=data["unit_ids"]
            )
        )
        found = {str(u.id) for u in units}
        missing = [str(uid) for uid in data["unit_ids"] if str(uid) not in found]

        # Any unit belonging to someone else makes the whole call a not-found,
        # rather than silently recording the subset the caller happens to own.
        foreign = [
            u for u in units if not owns(request.membership, u.batch.product.manufacturer)
        ]
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


class PrintScanSerializer(serializers.Serializer):
    batch = serializers.UUIDField()
    #: The raw token read from the printed code. Never stored, never logged,
    #: never echoed back in the response.
    token = serializers.CharField(max_length=100, trim_whitespace=True)


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
@throttle_classes([PrintScanThrottle])
def print_scans(request):
    """Record one printed code read back on the print line.

    Unlike the rest of the manufacturing records, this is evidence rather than
    an assertion, so it is stored as such. It is also the only staff endpoint
    that handles a raw token: the value is hashed and compared, and no part of
    it reaches the response, the stored event or the audit trail.
    """
    serializer = PrintScanSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    batch = (
        Batch.objects.select_related("product__manufacturer")
        .filter(pk=data["batch"])
        .first()
    )
    if batch is None or not owns(request.membership, batch.product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such batch."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        result = record_print_scan(
            batch=batch,
            token=data["token"],
            recorded_by=request.user,
            scanned_at=timezone.now(),
        )
    except ScanNotMatched as exc:
        # 200 with an outcome, not an error status: an operator working through
        # a tray of labels needs to be told which one did not belong, and a
        # stream of 4xx responses in the log is not that.
        return Response(
            {"outcome": "NOT_MATCHED", "detail": str(exc), **_progress(batch)}
        )
    except ScanNotApplicable as exc:
        return Response(
            {"outcome": "NOT_APPLICABLE", "detail": str(exc), **_progress(batch)}
        )

    unit = result["unit"]
    if not result["already_scanned"]:
        outcome = "RECORDED"
    elif result["previously_scanned"]:
        outcome = "ALREADY_SCANNED"
    else:
        outcome = "ALREADY_RECORDED"

    return Response(
        {
            "outcome": outcome,
            "external_reference": unit.external_reference,
            **_progress(batch),
        }
    )


def _progress(batch) -> dict:
    """The running totals the person scanning, and the release manager, watch."""
    progress = batch_manufacturing_progress(batch.id)
    return {
        "units_scan_verified": progress["units_scan_verified"],
        "units_ready": progress["units_ready"],
        "units_total": PackageUnit.objects.filter(batch=batch).count(),
    }
