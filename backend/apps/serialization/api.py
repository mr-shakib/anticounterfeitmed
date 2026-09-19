"""Print jobs and the controlled label export.

The export is the one place raw tokens leave the system. It is returned exactly
once, in the response to the call that generates it, and never stored or
retrievable afterwards -- so this endpoint is also the only staff surface that
must never be logged with its body.
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.catalog.models import Batch
from apps.organizations.permissions import STAFF_AUTH, IsManufacturerStaff, owns
from apps.serialization.models import PackageUnit, PrintJob
from apps.serialization.export_store import ExportUnavailable, decrypt_export
from apps.serialization.services import (
    IssuanceNotPermitted,
    create_print_job,
    reconcile_print_job,
)


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
                {
                    "external_reference": unit.external_reference,
                    "qr_url": f"https://anticounterfeitmed.com/#v=1&t={unit.token}",
                }
                for unit in result.units
            ],
            "export_notice": (
                "These URLs are shown once and cannot be retrieved again. "
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

    counts: dict[str, int] = {}
    for unit in PackageUnit.objects.filter(batch=batch).values_list("lifecycle", flat=True):
        counts[unit] = counts.get(unit, 0) + 1

    return Response(
        {
            "counts_by_lifecycle": counts,
            "units": UnitSerializer(queryset[:500], many=True).data,
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
        labels = decrypt_export(job.export_ciphertext)
    except ExportUnavailable as exc:
        return Response(
            {"code": "EXPORT_UNAVAILABLE", "detail": str(exc)},
            status=status.HTTP_410_GONE,
        )

    return Response(
        {
            "print_job": PrintJobSerializer(job).data,
            "label_export": [
                {
                    "external_reference": entry["external_reference"],
                    "qr_url": f"https://anticounterfeitmed.com/#v=1&t={entry['token']}",
                }
                for entry in labels
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

    reconcile_print_job(
        job=job,
        printed=serializer.validated_data["printed"],
        rejected=serializer.validated_data["rejected"],
        actor_description=request.user.get_username(),
    )
    return Response(PrintJobSerializer(job).data)
