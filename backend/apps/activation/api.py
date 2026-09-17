"""Activation, recall and unit blocking.

Activation reports per-unit results honestly: a run with failures is never
described as a completed batch, and the response says which units failed and
why so the portal can show it rather than rounding up to success.
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.activation.models import ActivationJob
from apps.activation.services import ActivationNotPermitted, activate_units, retry_failed
from apps.catalog.models import Batch
from apps.organizations.permissions import (
    STAFF_AUTH,
    IsManufacturerStaff,
    IsReleaseManager,
    IsStaff,
    owns,
)
from apps.serialization.models import PackageUnit


class ActivationRequestSerializer(serializers.Serializer):
    batch = serializers.UUIDField()
    unit_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, min_length=1, max_length=10_000
    )


class RecallSerializer(serializers.Serializer):
    notice = serializers.CharField(max_length=4000)
    contact = serializers.CharField(max_length=300, required=False, allow_blank=True)


class BlockSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


def _job_payload(job: ActivationJob) -> dict:
    return {
        "id": str(job.id),
        "approval_id": job.approval_id,
        "status": job.status,
        "requested": job.requested_count,
        "succeeded": job.succeeded_count,
        "failed": job.failed_count,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "failures": [
            {"unit_id": str(item.unit_id), "reason": item.failure_reason}
            for item in job.items.filter(succeeded=False)[:200]
        ],
    }


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsReleaseManager])
def activation_jobs(request):
    serializer = ActivationRequestSerializer(data=request.data)
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

    unit_ids = serializer.validated_data.get("unit_ids")
    queryset = PackageUnit.objects.filter(batch=batch)
    if unit_ids:
        queryset = queryset.filter(pk__in=unit_ids)
    units = list(queryset)

    if not units:
        return Response(
            {"code": "NO_UNITS", "detail": "No units matched."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        outcome = activate_units(batch=batch, units=units, membership=request.membership)
    except ActivationNotPermitted as exc:
        return Response(
            {"code": "ACTIVATION_NOT_PERMITTED", "detail": str(exc)},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response(_job_payload(outcome.job), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsManufacturerStaff])
def activation_job_detail(request, job_id):
    job = ActivationJob.objects.filter(pk=job_id).select_related("organization").first()
    if job is None or not owns(request.membership, job.organization):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such activation job."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(_job_payload(job))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsReleaseManager])
def activation_job_retry(request, job_id):
    """Re-attempt only the units that failed."""
    job = ActivationJob.objects.filter(pk=job_id).select_related("organization").first()
    if job is None or not owns(request.membership, job.organization):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such activation job."},
            status=status.HTTP_404_NOT_FOUND,
        )
    outcome = retry_failed(job=job, membership=request.membership)
    return Response(_job_payload(outcome.job))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsReleaseManager])
def recall_batch(request, batch_id):
    """Publish a recall.

    A recall prevents later first redemptions. It does not erase verifications
    that already happened: both facts stay visible.
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.audit.models import AuditAction, AuditEvent

    serializer = RecallSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    batch = (
        Batch.objects.select_related("product__manufacturer").filter(pk=batch_id).first()
    )
    if batch is None or not owns(request.membership, batch.product.manufacturer):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such batch."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if batch.is_recalled:
        return Response(
            {"code": "ALREADY_RECALLED", "detail": "This batch is already recalled."},
            status=status.HTTP_409_CONFLICT,
        )

    with transaction.atomic():
        # Same lock order as the confirmation transaction: organization, then
        # batch. A recall racing a scan must serialise, not deadlock.
        locked_org = type(batch.product.manufacturer).objects.select_for_update().get(
            pk=batch.product.manufacturer_id
        )
        locked = Batch.objects.select_for_update().get(pk=batch.pk)
        locked.is_recalled = True
        locked.recalled_at = timezone.now()
        locked.recall_notice = serializer.validated_data["notice"]
        locked.recall_contact = serializer.validated_data.get("contact", "")
        locked.save(
            update_fields=["is_recalled", "recalled_at", "recall_notice", "recall_contact"]
        )
        AuditEvent.objects.create(
            action=AuditAction.BATCH_RECALLED,
            organization=locked_org,
            batch_id=locked.id,
            actor_user=request.user,
            reason=serializer.validated_data["notice"],
        )

    return Response({"batch": str(batch.id), "is_recalled": True})


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsStaff])
def block_unit(request, unit_id):
    """Restrict a unit with an audited reason.

    Available to the owning manufacturer and to a platform admin, since
    emergency restriction is an admin function too.
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.audit.models import AuditAction, AuditEvent
    from apps.organizations.models import StaffRole

    serializer = BlockSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    unit = (
        PackageUnit.objects.select_related("batch__product__manufacturer")
        .filter(pk=unit_id)
        .first()
    )
    is_admin = request.membership.role == StaffRole.PLATFORM_ADMIN
    if unit is None or not (is_admin or owns(request.membership, unit.batch.product.manufacturer)):
        return Response(
            {"code": "NOT_FOUND", "detail": "No such unit."},
            status=status.HTTP_404_NOT_FOUND,
        )

    with transaction.atomic():
        locked = PackageUnit.objects.select_for_update().get(pk=unit.pk)
        locked.is_blocked = True
        locked.blocked_at = timezone.now()
        locked.blocked_reason = serializer.validated_data["reason"]
        locked.save(update_fields=["is_blocked", "blocked_at", "blocked_reason"])
        AuditEvent.objects.create(
            action=AuditAction.UNIT_BLOCKED,
            organization=unit.batch.product.manufacturer,
            unit_id=locked.id,
            batch_id=locked.batch_id,
            actor_user=request.user,
            reason=serializer.validated_data["reason"],
        )

    return Response({"unit": str(unit.id), "is_blocked": True})
