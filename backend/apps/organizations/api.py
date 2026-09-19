"""Staff authentication and the caller's own context.

Login is two steps for privileged roles: password, then a second factor. The
session is not treated as privileged until the second step completes, so an
attacker holding only a password reaches nothing a release manager can do.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.audit.models import AuditAction, AuditEvent
from apps.organizations import mfa
from apps.organizations.models import StaffMembership
from apps.organizations.permissions import (
    STAFF_AUTH,
    IsPlatformAdmin,
    MFA_SESSION_KEY,
    IsStaff,
    membership_for,
    session_mfa_ok,
    staff_mfa_required,
)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)


def _membership_payload(membership: StaffMembership, request) -> dict:
    return {
        "membership_id": str(membership.id),
        "username": membership.user.get_username(),
        "role": membership.role,
        "organization": {
            "id": str(membership.organization_id),
            "name": membership.organization.name,
            "type": membership.organization.type,
            "approval_status": membership.organization.approval_status,
            "is_suspended": membership.organization.is_suspended,
        },
        # False when the second factor is switched off for local work, so the
        # portal goes straight in rather than asking for a code nothing checks.
        # Whether a code is needed right now: only when one is enrolled.
        "mfa_required": membership.has_mfa,
        # Whether enrolling is compulsory before this role can work.
        "mfa_enrolment_required": membership.is_privileged and staff_mfa_required(),
        "mfa_enrolled": membership.has_mfa,
        "mfa_verified": session_mfa_ok(request, membership),
    }


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([AllowAny])
def staff_login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = authenticate(
        request,
        username=serializer.validated_data["username"],
        password=serializer.validated_data["password"],
    )
    if user is None:
        # Deliberately unspecific: it does not say whether the account exists.
        return Response(
            {"code": "INVALID_CREDENTIALS", "detail": "Login failed."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    login(request, user)
    membership = membership_for(request)
    if membership is None:
        logout(request)
        return Response(
            {"code": "NO_MEMBERSHIP", "detail": "This account has no enabled membership."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # A fresh session has not cleared the second factor yet.
    request.session.pop(MFA_SESSION_KEY, None)
    return Response(_membership_payload(membership, request))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([AllowAny])
def staff_logout(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsStaff])
def whoami(request):
    return Response(_membership_payload(request.membership, request))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([AllowAny])
def mfa_enroll(request):
    """Begin enrolment, returning a provisioning URI to scan.

    Requires a password-authenticated session. The secret is only usable once
    confirmed with a code, so an interrupted enrolment leaves nothing active.
    """
    membership = membership_for(request)
    if membership is None:
        return Response(
            {"code": "NOT_AUTHENTICATED", "detail": "Log in first."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if membership.has_mfa:
        return Response(
            {"code": "ALREADY_ENROLLED", "detail": "A second factor is already set."},
            status=status.HTTP_409_CONFLICT,
        )

    secret = mfa.new_secret()
    membership.totp_secret = secret
    membership.mfa_enabled = False
    membership.mfa_confirmed_at = None
    membership.save(update_fields=["totp_secret", "mfa_enabled", "mfa_confirmed_at"])

    account = f"{membership.user.get_username()}@{membership.organization.name}"
    return Response(
        {
            # Shown once, during enrolment only.
            "secret": secret,
            "provisioning_uri": mfa.provisioning_uri(secret, account),
        }
    )


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([AllowAny])
def mfa_confirm(request):
    """Complete enrolment by proving possession of the secret."""
    membership = membership_for(request)
    if membership is None:
        return Response(
            {"code": "NOT_AUTHENTICATED", "detail": "Log in first."},
            status=status.HTTP_403_FORBIDDEN,
        )
    serializer = CodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if not mfa.verify_code(membership.totp_secret, serializer.validated_data["code"]):
        return Response(
            {"code": "INVALID_CODE", "detail": "That code did not match."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    membership.mfa_enabled = True
    membership.mfa_confirmed_at = timezone.now()
    membership.save(update_fields=["mfa_enabled", "mfa_confirmed_at"])
    request.session[MFA_SESSION_KEY] = str(membership.id)
    return Response(_membership_payload(membership, request))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([AllowAny])
def mfa_verify(request):
    """Second step of login: clear the second factor for this session."""
    membership = membership_for(request)
    if membership is None:
        return Response(
            {"code": "NOT_AUTHENTICATED", "detail": "Log in first."},
            status=status.HTTP_403_FORBIDDEN,
        )
    serializer = CodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if not membership.has_mfa:
        return Response(
            {"code": "NOT_ENROLLED", "detail": "Enrol a second factor first."},
            status=status.HTTP_409_CONFLICT,
        )
    if not mfa.verify_code(membership.totp_secret, serializer.validated_data["code"]):
        return Response(
            {"code": "INVALID_CODE", "detail": "That code did not match."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    request.session[MFA_SESSION_KEY] = str(membership.id)
    return Response(_membership_payload(membership, request))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsStaff])
def mfa_disable(request):
    """Remove the caller's own second factor.

    Requires a current code, so someone who has walked away from an unlocked
    screen cannot quietly strip the protection off the account. Refused outright
    when policy makes enrolment compulsory for the role -- the way out there is
    an administrator reset, which is recorded.
    """
    membership = request.membership
    if not membership.has_mfa:
        return Response(
            {"code": "NOT_ENROLLED", "detail": "No second factor is set."},
            status=status.HTTP_409_CONFLICT,
        )
    if membership.is_privileged and staff_mfa_required():
        return Response(
            {
                "code": "MFA_COMPULSORY",
                "detail": (
                    "This role requires a second factor. An administrator can "
                    "reset it if the authenticator has been lost."
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = CodeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not mfa.verify_code(membership.totp_secret, serializer.validated_data["code"]):
        return Response(
            {"code": "INVALID_CODE", "detail": "That code did not match."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    membership.totp_secret = ""
    membership.mfa_enabled = False
    membership.mfa_confirmed_at = None
    membership.save(update_fields=["totp_secret", "mfa_enabled", "mfa_confirmed_at"])
    request.session.pop(MFA_SESSION_KEY, None)

    AuditEvent.objects.create(
        action=AuditAction.STAFF_MFA_RESET,
        organization=membership.organization,
        actor_user=request.user,
        reason=f"{request.user.get_username()} removed their own second factor",
        detail={"membership_id": str(membership.id), "action": "MFA_SELF_DISABLED"},
    )
    return Response(_membership_payload(membership, request))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def reset_membership_mfa(request, membership_id):
    """Clear a staff member's second factor so they can enrol again.

    Someone who loses their phone would otherwise be locked out of a privileged
    role permanently. Clearing it does not grant access: the next login lands in
    enrolment and cannot proceed without completing it.
    """
    membership = StaffMembership.objects.filter(pk=membership_id).first()
    if membership is None:
        return Response({"code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

    membership.totp_secret = ""
    membership.mfa_enabled = False
    membership.mfa_confirmed_at = None
    membership.save(update_fields=["totp_secret", "mfa_enabled", "mfa_confirmed_at"])

    AuditEvent.objects.create(
        action=AuditAction.STAFF_MFA_RESET,
        organization=membership.organization,
        actor_user=request.user,
        reason="Second factor reset for "
        f"{membership.user.get_username()} by {request.user.get_username()}",
        detail={"membership_id": str(membership.id), "action": "MFA_RESET"},
    )
    return Response({"membership_id": str(membership.id), "mfa_enrolled": False})


@api_view(["GET"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def list_memberships(request):
    """Staff across all organizations, for access review."""
    memberships = StaffMembership.objects.select_related(
        "user", "organization"
    ).order_by("organization__name", "user__username")
    return Response(
        [
            {
                "membership_id": str(m.id),
                "username": m.user.get_username(),
                "organization": m.organization.name,
                "role": m.role,
                "is_enabled": m.is_enabled,
                "mfa_required": m.is_privileged,
                "mfa_enrolled": m.has_mfa,
            }
            for m in memberships
        ]
    )
