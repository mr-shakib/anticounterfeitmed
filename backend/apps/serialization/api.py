"""Print jobs and the controlled label export.

The export is the one place raw tokens leave the system. It is returned exactly
once, in the response to the call that generates it, and never stored or
retrievable afterwards -- so this endpoint is also the only staff surface that
must never be logged with its body.
"""

from __future__ import annotations

import re
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from medcrypto import labels

from apps.audit.models import AuditAction, AuditEvent
from apps.catalog.models import Batch
from apps.organizations.permissions import STAFF_AUTH, IsManufacturerStaff, owns
from apps.qc.services import batch_manufacturing_progress
from apps.serialization.models import (
    LABEL_FOOTPRINTS_MM,
    LabelLayout,
    PackageUnit,
    PrintJob,
)
from apps.serialization.export_store import ExportUnavailable, decrypt_export
from apps.serialization.services import (
    IssuanceNotPermitted,
    create_print_job,
    reconcile_print_job,
)


def label_entry(external_reference: str, token: str) -> dict:
    """One label as the portal needs it to draw the printed symbol.

    The symbol's data codewords rather than a URL: a generic scanner reads only
    the public URL from the printed code, and the token rides after it where
    only our own readers look (see ``medcrypto.labels``). Drawing the symbol is
    left to the portal, which has to render thousands of them anyway.
    """
    return {
        "external_reference": external_reference,
        "qr": {
            "version": labels.SYMBOL_VERSION,
            "error_correction": labels.ERROR_CORRECTION,
            "data_codewords": labels.data_codewords(token).hex(),
        },
    }


class PrintJobSerializer(serializers.ModelSerializer):
    export_available = serializers.SerializerMethodField()
    export_expires_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = PrintJob
        fields = [
            "id", "batch", "planned_count", "issued_count", "status",
            "reconciled_at", "reconciled_printed", "reconciled_rejected",
            "export_available", "export_expires_at", "export_deleted_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_export_available(self, job: PrintJob) -> bool:
        from django.utils import timezone

        return job.export_available(timezone.now())


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackageUnit
        fields = [
            "id", "external_reference", "lifecycle", "is_blocked",
            "blocked_reason", "version", "activated_at", "redeemed_at",
        ]
        read_only_fields = fields
        # token_sha256 is absent by design. A digest is not something an
        # operator needs, and shipping it invites treating it as a lookup key.


class CreatePrintJobSerializer(serializers.Serializer):
    batch = serializers.UUIDField()
    count = serializers.IntegerField(min_value=1, max_value=100_000)


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def print_jobs(request):
    serializer = CreatePrintJobSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    batch = (
        Batch.objects.select_related("product__manufacturer")
        .filter(pk=serializer.validated_data["batch"])
        .first()
    )
    if batch is None or not owns(request.membership, batch.product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such batch."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        result = create_print_job(
            batch=batch,
            count=serializer.validated_data["count"],
            created_by=request.user.get_username(),
        )
    except IssuanceNotPermitted as exc:
        return Response(
            {"code": "ISSUANCE_NOT_PERMITTED", "detail": str(exc)},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "print_job": PrintJobSerializer(result.print_job).data,
            # Returned once. Nothing can recover these afterwards, so the
            # client must write the export before discarding the response.
            "label_export": [
                label_entry(unit.external_reference, unit.token)
                for unit in result.units
            ],
            "export_notice": (
                "These labels are shown once and cannot be retrieved again. "
                "Save the export now, print from it, and delete it within 24 "
                "hours of reconciling the job."
            ),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def batch_units(request, batch_id):
    batch = (
        Batch.objects.select_related("product__manufacturer").filter(pk=batch_id).first()
    )
    if batch is None or not owns(request.membership, batch.product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such batch."},
            status=status.HTTP_404_NOT_FOUND,
        )

    queryset = PackageUnit.objects.filter(batch=batch).order_by("external_reference")
    lifecycle = request.query_params.get("lifecycle")
    if lifecycle:
        queryset = queryset.filter(lifecycle=lifecycle)
    if request.query_params.get("blocked") == "true":
        queryset = queryset.filter(is_blocked=True)
    # Search by the reference printed beside the code -- what someone holding a
    # strip can read off it.
    search = request.query_params.get("q", "").strip()
    if search:
        queryset = queryset.filter(external_reference__icontains=search)

    try:
        offset = max(int(request.query_params.get("offset", 0)), 0)
        limit = min(max(int(request.query_params.get("limit", 500)), 1), 500)
    except ValueError:
        return Response(
            {"code": "BAD_PAGE", "detail": "offset and limit must be whole numbers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    counts: dict[str, int] = {}
    for unit in PackageUnit.objects.filter(batch=batch).values_list("lifecycle", flat=True):
        counts[unit] = counts.get(unit, 0) + 1

    return Response(
        {
            "counts_by_lifecycle": counts,
            "units_blocked": PackageUnit.objects.filter(batch=batch, is_blocked=True).count(),
            # Manufacturer-asserted records, not captured scan evidence. The
            # portal labels them as such.
            **batch_manufacturing_progress(batch.id),
            "units_matching": queryset.count(),
            "offset": offset,
            "units": UnitSerializer(queryset[offset : offset + limit], many=True).data,
        }
    )


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def batch_print_jobs(request, batch_id):
    """The print jobs for a batch, and whether their labels can still be had."""
    batch = (
        Batch.objects.select_related("product__manufacturer").filter(pk=batch_id).first()
    )
    if batch is None or not owns(request.membership, batch.product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such batch."},
            status=status.HTTP_404_NOT_FOUND,
        )
    jobs = PrintJob.objects.filter(batch=batch).order_by("-created_at")
    return Response(PrintJobSerializer(jobs, many=True).data)


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def print_job_export(request, job_id):
    """Return a retained label export.

    Available until the job is reconciled, and for a short grace period after.
    Once that passes the export is deleted and the labels cannot be recovered:
    replacing lost labels means voiding those units and issuing new ones, which
    leaves a record.
    """
    from django.utils import timezone

    job = (
        PrintJob.objects.select_related("batch__product__manufacturer", "manufacturer")
        .filter(pk=job_id)
        .first()
    )
    if job is None or not owns(request.membership, job.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such print job."},
            status=status.HTTP_404_NOT_FOUND,
        )

    now = timezone.now()
    if not job.export_available(now):
        return Response(
            {
                "code": "EXPORT_UNAVAILABLE",
                "detail": (
                    "The labels for this job are no longer retrievable. Void the "
                    "affected units and issue replacements."
                ),
                "expired_at": job.export_expires_at,
                "deleted_at": job.export_deleted_at,
            },
            status=status.HTTP_410_GONE,
        )

    try:
        retained = decrypt_export(job.export_ciphertext)
    except ExportUnavailable as exc:
        return Response(
            {"code": "EXPORT_UNAVAILABLE", "detail": str(exc)},
            status=status.HTTP_410_GONE,
        )

    return Response(
        {
            "print_job": PrintJobSerializer(job).data,
            "label_export": [
                label_entry(entry["external_reference"], entry["token"])
                for entry in retained
            ],
            "export_notice": (
                "Retrievable until "
                f"{job.export_expires_at:%Y-%m-%d %H:%M} UTC, then deleted. "
                "Keep it under the same controls as the printed labels."
            ),
        }
    )


class ReconcileSerializer(serializers.Serializer):
    printed = serializers.IntegerField(min_value=0)
    rejected = serializers.IntegerField(min_value=0)


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def reconcile_job(request, job_id):
    """Record printed and rejected counts, which starts the export's deletion clock."""
    serializer = ReconcileSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    job = PrintJob.objects.select_related("manufacturer").filter(pk=job_id).first()
    if job is None or not owns(request.membership, job.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such print job."},
            status=status.HTTP_404_NOT_FOUND,
        )
    for field in ("printed", "rejected"):
        if serializer.validated_data[field] > job.issued_count:
            return Response(
                {
                    "code": "COUNT_EXCEEDS_ISSUED",
                    "detail": f"Only {job.issued_count} labels were issued in this run.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    reconcile_print_job(
        job=job,
        printed=serializer.validated_data["printed"],
        rejected=serializer.validated_data["rejected"],
        actor_description=request.user.get_username(),
    )
    return Response(PrintJobSerializer(job).data)


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class LabelLayoutSerializer(serializers.ModelSerializer):
    page_margin_mm = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=Decimal("0"), max_value=Decimal("50"),
        coerce_to_string=False, required=False,
    )
    gap_mm = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=Decimal("0"), max_value=Decimal("100"),
        coerce_to_string=False, required=False,
    )
    footprint_mm = serializers.ChoiceField(choices=LABEL_FOOTPRINTS_MM, required=False)

    class Meta:
        model = LabelLayout
        fields = [
            "page_size", "page_margin_mm", "gap_mm", "footprint_mm",
            "show_header", "header_text", "show_reference", "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_header_text(self, value: str) -> str:
        # One line on the page. A line break or a control character would
        # print differently in the HTML sheet and the PDF.
        if _CONTROL_CHARACTERS.search(value):
            raise serializers.ValidationError("The header must be a single line of text.")
        return value


def _layout_detail(layout: LabelLayout) -> dict:
    """The layout as plain JSON, for the audit record."""
    data = LabelLayoutSerializer(layout).data
    data.pop("updated_at")
    return {
        key: float(value) if isinstance(value, Decimal) else value
        for key, value in data.items()
    }


@api_view(["GET", "PATCH"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def label_layout(request):
    """The caller's organization's label sheet layout.

    Applies to every printable sheet and PDF the portal draws for that
    organization. Until someone saves one, the defaults put nothing on the page
    but the codes. A field left out of a change keeps its current value.
    """
    org = request.membership.organization
    if request.method == "GET":
        layout = LabelLayout.objects.filter(organization=org).first()
        return Response(LabelLayoutSerializer(layout or LabelLayout(organization=org)).data)

    serializer = LabelLayoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        LabelLayout.objects.get_or_create(organization=org)
        layout = LabelLayout.objects.select_for_update().get(organization=org)
        before = _layout_detail(layout)
        for field, value in serializer.validated_data.items():
            setattr(layout, field, value)
        layout.save()
        AuditEvent.objects.create(
            action=AuditAction.LABEL_LAYOUT_UPDATED,
            organization=org,
            actor_user=request.user,
            reason="Label sheet layout updated",
            detail={"before": before, "after": _layout_detail(layout)},
        )
    return Response(LabelLayoutSerializer(layout).data)
