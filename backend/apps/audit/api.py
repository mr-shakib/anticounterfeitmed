"""Platform administration: approvals, suspension, audit search, investigations.

Admin can restrict and investigate. It cannot edit signed data, reset a redeemed
unit, or activate on a manufacturer's behalf -- those are absent from this module
by design, not merely unimplemented.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.audit.models import AuditAction, AuditEvent
from apps.organizations.models import ApprovalStatus, Organization, OrganizationType
from apps.organizations.permissions import STAFF_AUTH, IsPlatformAdmin
from apps.reports.models import Report, ReportStatus
from apps.trust.services import (
    NoUsableKey,
    ensure_activation_key,
    organizations_with_activation_key,
)
from apps.trust.signing import SignerUnavailable


class OrganizationSerializer(serializers.ModelSerializer):
    has_signing_key = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id", "name", "type", "contact_email", "contact_phone",
            "approval_status", "approved_at", "is_suspended", "suspended_at",
            "suspension_reason", "has_signing_key", "created_at",
        ]
        read_only_fields = ["id", "approved_at", "suspended_at", "created_at"]

    def get_has_signing_key(self, org: Organization) -> bool:
        keyed = self.context.get("keyed")
        if keyed is None:
            keyed = organizations_with_activation_key([org.id])
        return org.id in keyed


class CreateOrganizationSerializer(serializers.ModelSerializer):
    """A manufacturer, entered by the platform. It starts pending approval."""

    class Meta:
        model = Organization
        fields = ["name", "contact_email", "contact_phone"]
        extra_kwargs = {"contact_email": {"required": True, "allow_blank": False}}

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if Organization.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("An organization with this name already exists.")
        return value


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


@api_view(["GET", "POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def organizations(request):
    if request.method == "POST":
        serializer = CreateOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            org = serializer.save(
                type=OrganizationType.MANUFACTURER,
                approval_status=ApprovalStatus.PENDING,
            )
            AuditEvent.objects.create(
                action=AuditAction.ORGANIZATION_CREATED,
                organization=org,
                actor_user=request.user,
            )
        return Response(OrganizationSerializer(org).data, status=status.HTTP_201_CREATED)

    queryset = Organization.objects.all().order_by("name")
    state = request.query_params.get("approval_status")
    if state:
        queryset = queryset.filter(approval_status=state)
    rows = list(queryset)
    keyed = organizations_with_activation_key([o.id for o in rows])
    return Response(OrganizationSerializer(rows, many=True, context={"keyed": keyed}).data)


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def approve_organization(request, organization_id):
    """Approve a manufacturer to issue and activate.

    Approval must be recorded before production issuance, so this is the gate
    that lets a manufacturer generate its first serial. It is also where the
    issuer-key association docs/10 asks for is made: a manufacturer without a
    key is given one here, so an approved manufacturer can always activate.
    Either both happen or neither does.
    """
    org = Organization.objects.filter(pk=organization_id).first()
    if org is None:
        return Response({"code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

    try:
        with transaction.atomic():
            key = (
                ensure_activation_key(org)
                if org.type == OrganizationType.MANUFACTURER
                else None
            )
            org.approval_status = ApprovalStatus.APPROVED
            org.approved_at = timezone.now()
            org.save(update_fields=["approval_status", "approved_at"])
            AuditEvent.objects.create(
                action=AuditAction.ORGANIZATION_APPROVED,
                organization=org,
                actor_user=request.user,
                detail={"signing_key_provisioned": key.key_id} if key else {},
            )
    except NoUsableKey:
        return Response(
            {
                "code": "NO_ROOT_KEY",
                "detail": (
                    "This instance has no root signing key yet. Run "
                    "infra/provision-keys.sh once, then approve again."
                ),
            },
            status=status.HTTP_409_CONFLICT,
        )
    except SignerUnavailable:
        return Response(
            {
                "code": "SIGNER_UNAVAILABLE",
                "detail": (
                    "The signing service did not respond, so no key could be "
                    "created. Nothing was approved; try again shortly."
                ),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(OrganizationSerializer(org).data)


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def suspend_organization(request, organization_id):
    """Suspend an issuer. Suspension overrides an otherwise positive result."""
    serializer = ReasonSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    org = Organization.objects.filter(pk=organization_id).first()
    if org is None:
        return Response({"code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        locked = Organization.objects.select_for_update().get(pk=org.pk)
        locked.is_suspended = True
        locked.suspended_at = timezone.now()
        locked.suspension_reason = serializer.validated_data["reason"]
        locked.save(update_fields=["is_suspended", "suspended_at", "suspension_reason"])
        AuditEvent.objects.create(
            action=AuditAction.ORGANIZATION_SUSPENDED,
            organization=locked,
            actor_user=request.user,
            reason=serializer.validated_data["reason"],
        )
    # Return the row that was actually written, not the stale copy fetched
    # before the lock.
    return Response(OrganizationSerializer(locked).data)


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def audit_search(request):
    """Search the audit trail by actor, organization, unit, action or request id."""
    queryset = AuditEvent.objects.select_related("organization", "actor_user")

    for param, field in (
        ("action", "action"),
        ("organization", "organization_id"),
        ("unit", "unit_id"),
        ("batch", "batch_id"),
        ("request_id", "request_id"),
    ):
        value = request.query_params.get(param)
        if value:
            queryset = queryset.filter(**{field: value})

    events = queryset.order_by("-created_at")[:200]
    return Response(
        [
            {
                "id": str(e.id),
                "action": e.action,
                "organization": e.organization.name if e.organization else None,
                "actor": e.actor_user.get_username() if e.actor_user else e.actor_description,
                "unit_id": str(e.unit_id) if e.unit_id else None,
                "batch_id": str(e.batch_id) if e.batch_id else None,
                "reason": e.reason,
                "request_id": e.request_id,
                "detail": e.detail,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    )


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def investigation_queue(request):
    queryset = Report.objects.select_related("organization", "assigned_to")
    state = request.query_params.get("status", ReportStatus.OPEN)
    if state != "all":
        queryset = queryset.filter(status=state)
    reason = request.query_params.get("reason")
    if reason:
        queryset = queryset.filter(reason=reason)

    return Response(
        [
            {
                "case_number": r.case_number,
                "reason": r.reason,
                "status": r.status,
                "organization": r.organization.name if r.organization else None,
                "unit_id": str(r.unit_id) if r.unit_id else None,
                "external_reference": r.external_reference,
                "assigned_to": r.assigned_to.get_username() if r.assigned_to else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in queryset.order_by("-created_at")[:200]
        ]
    )


class ConclusionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c[0] for c in ReportStatus.choices])
    conclusion = serializers.CharField(max_length=4000, required=False, allow_blank=True)


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def conclude_report(request, case_number):
    """Record a finding. This adds to the case; it never erases history."""
    serializer = ConclusionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    report = Report.objects.filter(case_number=case_number).first()
    if report is None:
        return Response({"code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

    report.status = serializer.validated_data["status"]
    report.conclusion = serializer.validated_data.get("conclusion", report.conclusion)
    report.assigned_to = request.user
    if report.status == ReportStatus.CLOSED:
        report.closed_at = timezone.now()
    report.save(update_fields=["status", "conclusion", "assigned_to", "closed_at"])
    return Response({"case_number": report.case_number, "status": report.status})


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def operational_dashboard(request):
    """Counts the admin workspace needs on one screen."""
    from apps.activation.models import ActivationJob, ActivationJobStatus
    from apps.verification.models import (
        ReceiptStatus,
        SignedReceipt,
        VerificationEvent,
        VerificationEventType,
    )

    return Response(
        {
            "organizations_pending": Organization.objects.filter(
                approval_status=ApprovalStatus.PENDING
            ).count(),
            "organizations_suspended": Organization.objects.filter(is_suspended=True).count(),
            "activation_jobs_with_failures": ActivationJob.objects.filter(
                status__in=[
                    ActivationJobStatus.COMPLETED_WITH_FAILURES,
                    ActivationJobStatus.FAILED,
                ]
            ).count(),
            "receipts_pending": SignedReceipt.objects.filter(
                status=ReceiptStatus.PENDING
            ).count(),
            "receipts_failed": SignedReceipt.objects.filter(
                status=ReceiptStatus.FAILED
            ).count(),
            "reports_open": Report.objects.filter(status=ReportStatus.OPEN).count(),
            "first_verifications": VerificationEvent.objects.filter(
                event_type=VerificationEventType.FIRST_REDEMPTION
            ).count(),
            "repeat_checks": VerificationEvent.objects.filter(
                event_type=VerificationEventType.REPEAT_CHECK
            ).count(),
        }
    )
