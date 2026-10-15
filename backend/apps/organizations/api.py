"""Staff authentication and the caller's own context.

Login is two steps for privileged roles: password, then a second factor. The
session is not treated as privileged until the second step completes, so an
attacker holding only a password reaches nothing a release manager can do.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    password_validation,
    update_session_auth_hash,
)
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
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
from apps.organizations.models import (
    Organization,
    OrganizationType,
    StaffMembership,
    StaffRole,
)
from apps.organizations.permissions import (
    STAFF_AUTH,
    IsPlatformAdmin,
    MFA_SESSION_KEY,
    IsStaff,
    membership_for,
    session_mfa_ok,
    staff_mfa_required,
)

User = get_user_model()

#: Which roles each kind of organization can hold. A manufacturer never has a
#: platform admin, and the platform never has a release manager.
ROLES_FOR_ORGANIZATION = {
    OrganizationType.PLATFORM: {StaffRole.PLATFORM_ADMIN},
    OrganizationType.MANUFACTURER: {StaffRole.RELEASE_MANAGER, StaffRole.MANUFACTURER_STAFF},
}


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=256, trim_whitespace=False)
    new_password = serializers.CharField(max_length=256, trim_whitespace=False)


class CreateMembershipSerializer(serializers.Serializer):
    organization = serializers.UUIDField()
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    role = serializers.ChoiceField(choices=[c[0] for c in StaffRole.choices])


class RevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


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
        # An administrator set a temporary password; nothing else works until
        # the owner replaces it.
        "password_change_required": membership.password_change_required,
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
@permission_classes([AllowAny])
def change_password(request):
    """Replace the caller's password.

    Reachable with a password-authenticated session alone, because that is all
    someone holding an administrator's temporary password has. Where a second
    factor is enrolled it must have been cleared first: otherwise a leaked
    password would be enough to lock the owner out of their own account.
    """
    membership = membership_for(request)
    if membership is None:
        return Response(
            {"code": "NOT_AUTHENTICATED", "detail": "Log in first."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if membership.has_mfa and not session_mfa_ok(request, membership):
        return Response(
            {"code": "MFA_REQUIRED", "detail": "Enter your second-factor code first."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = PasswordChangeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = membership.user
    current = serializer.validated_data["current_password"]
    new = serializer.validated_data["new_password"]

    if not user.check_password(current):
        return Response(
            {"code": "INVALID_CREDENTIALS", "detail": "The current password is not correct."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if new == current:
        return Response(
            {"code": "PASSWORD_UNCHANGED", "detail": "Choose a password you have not used here."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        password_validation.validate_password(new, user)
    except DjangoValidationError as exc:
        return Response(
            {"code": "WEAK_PASSWORD", "detail": " ".join(exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        user.set_password(new)
        user.save(update_fields=["password"])
        StaffMembership.objects.filter(user=user).update(password_change_required=False)
        AuditEvent.objects.create(
            action=AuditAction.STAFF_PASSWORD_CHANGED,
            organization=membership.organization,
            actor_user=user,
            detail={"membership_id": str(membership.id)},
        )

    # Changing the password rotates the session hash; keep this session signed
    # in rather than sending the person straight back to the login form.
    update_session_auth_hash(request, user)
    membership.refresh_from_db()
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


def _staff_row(m: StaffMembership) -> dict:
    return {
        "membership_id": str(m.id),
        "username": m.user.get_username(),
        "organization": m.organization.name,
        "organization_id": str(m.organization_id),
        "role": m.role,
        "is_enabled": m.is_enabled,
        "disabled_at": m.disabled_at.isoformat() if m.disabled_at else None,
        "password_change_required": m.password_change_required,
        "mfa_required": m.is_privileged,
        "mfa_enrolled": m.has_mfa,
    }


@api_view(["GET", "POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def memberships(request):
    """Staff across all organizations, for access review -- and adding to them.

    A new account gets a temporary password generated here and returned once.
    It opens nothing but the password-change step, so the administrator who saw
    it cannot go on using it after the owner has signed in. The password is not
    stored anywhere but the hash, and never reaches the audit record.
    """
    if request.method == "GET":
        rows = StaffMembership.objects.select_related("user", "organization").order_by(
            "organization__name", "user__username"
        )
        return Response([_staff_row(m) for m in rows])

    serializer = CreateMembershipSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    organization = Organization.objects.filter(pk=data["organization"]).first()
    if organization is None:
        return Response(
            {"code": "NOT_FOUND", "detail": "No such organization."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if data["role"] not in ROLES_FOR_ORGANIZATION.get(organization.type, set()):
        return Response(
            {
                "code": "ROLE_NOT_ALLOWED",
                "detail": f"A {organization.get_type_display().lower()} cannot hold that role.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if User.objects.filter(username__iexact=data["username"]).exists():
        return Response(
            {"code": "USERNAME_TAKEN", "detail": "That username is already in use."},
            status=status.HTTP_409_CONFLICT,
        )

    temporary_password = secrets.token_urlsafe(12)
    with transaction.atomic():
        user = User.objects.create_user(
            username=data["username"], password=temporary_password
        )
        membership = StaffMembership.objects.create(
            user=user,
            organization=organization,
            role=data["role"],
            password_change_required=True,
        )
        AuditEvent.objects.create(
            action=AuditAction.STAFF_CREATED,
            organization=organization,
            actor_user=request.user,
            reason=f"{user.get_username()} added as {membership.get_role_display().lower()}",
            detail={"membership_id": str(membership.id), "role": membership.role},
        )

    membership = StaffMembership.objects.select_related("user", "organization").get(
        pk=membership.pk
    )
    response = Response(
        {**_staff_row(membership), "temporary_password": temporary_password},
        status=status.HTTP_201_CREATED,
    )
    # Holds a credential: nothing between here and the browser may keep it.
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def disable_membership(request, membership_id):
    """Revoke a staff member's access, with a reason. Takes effect on their next request."""
    serializer = RevokeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    membership = (
        StaffMembership.objects.select_related("user", "organization")
        .filter(pk=membership_id)
        .first()
    )
    if membership is None:
        return Response({"code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
    if membership.pk == request.membership.pk:
        # Otherwise the last administrator could lock the platform out of itself.
        return Response(
            {"code": "CANNOT_DISABLE_SELF", "detail": "You cannot revoke your own access."},
            status=status.HTTP_409_CONFLICT,
        )

    with transaction.atomic():
        membership.is_enabled = False
        membership.disabled_at = timezone.now()
        membership.save(update_fields=["is_enabled", "disabled_at"])
        AuditEvent.objects.create(
            action=AuditAction.STAFF_DISABLED,
            organization=membership.organization,
            actor_user=request.user,
            reason=serializer.validated_data["reason"],
            detail={"membership_id": str(membership.id), "username": membership.user.get_username()},
        )
    return Response(_staff_row(membership))


@api_view(["POST"])
@authentication_classes(STAFF_AUTH)
@permission_classes([IsPlatformAdmin])
def enable_membership(request, membership_id):
    """Restore access revoked by mistake. Recorded like the revocation was."""
    membership = (
        StaffMembership.objects.select_related("user", "organization")
        .filter(pk=membership_id)
        .first()
    )
    if membership is None:
        return Response({"code": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        membership.is_enabled = True
        membership.disabled_at = None
        membership.save(update_fields=["is_enabled", "disabled_at"])
        AuditEvent.objects.create(
            action=AuditAction.STAFF_ENABLED,
            organization=membership.organization,
            actor_user=request.user,
            detail={"membership_id": str(membership.id), "username": membership.user.get_username()},
        )
    return Response(_staff_row(membership))
