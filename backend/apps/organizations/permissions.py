"""Staff authorization.

Two rules run through everything here.

Scoping is by membership, never by anything the caller sends. A request never
names the organization it is acting for: that comes from the authenticated
membership, so a manufacturer cannot reach another's data by changing a field.

Privileged roles must hold a second factor, and the check is on the *session*
having completed it, not merely on the account having it enabled.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication

from apps.organizations.models import Organization, StaffMembership, StaffRole

#: Staff endpoints authenticate with the Django session. DRF has no global
#: default here on purpose, so a new view cannot inherit authority by accident
#: -- every staff view states this explicitly.
STAFF_AUTH = [SessionAuthentication]

MFA_SESSION_KEY = "mfa_verified_membership"


def membership_for(request) -> StaffMembership | None:
    """Resolve the caller's enabled membership, or None."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return (
        StaffMembership.objects.select_related("organization", "user")
        .filter(user=user, is_enabled=True)
        .first()
    )


def staff_mfa_required() -> bool:
    """Whether a privileged role must hold a second factor to work at all.

    Off by default: staff enrol from their own settings, and someone who has not
    enrolled can still sign in. Turning it on makes enrolment a precondition for
    privileged work, which is what docs/10 asks for in a pilot -- a release
    manager can put medicine into circulation and an admin can suspend an
    issuer, and a password alone is thin protection for either.

    This setting only governs whether enrolment is *compulsory*. A second factor
    that someone has enrolled is always demanded at sign-in, regardless.
    """
    return bool(getattr(settings, "STAFF_MFA_REQUIRED", False))


def session_mfa_ok(request, membership: StaffMembership) -> bool:
    """True when this session may act for this membership.

    Once someone has enrolled a second factor it is always required, whatever
    the policy says. Anything else would make enrolling pointless: an attacker
    with the password would simply not present a code.
    """
    if membership.has_mfa:
        return str(request.session.get(MFA_SESSION_KEY, "")) == str(membership.id)

    # No factor enrolled. Allowed unless policy makes enrolment compulsory for
    # this role.
    return not (membership.is_privileged and staff_mfa_required())


class IsStaff(permissions.BasePermission):
    """Any enabled membership, with MFA cleared where the role requires it."""

    message = "Staff authentication is required."

    def has_permission(self, request, view) -> bool:
        membership = membership_for(request)
        if membership is None:
            return False
        if not session_mfa_ok(request, membership):
            self.message = "Second factor required for this role."
            return False
        request.membership = membership
        return True


class IsPlatformAdmin(IsStaff):
    message = "Platform administrator access is required."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.membership.role == StaffRole.PLATFORM_ADMIN


class IsManufacturerStaff(IsStaff):
    """Any enabled member of an approved, unsuspended manufacturer."""

    message = "Manufacturer staff access is required."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        membership = request.membership
        return (
            membership.role in (StaffRole.RELEASE_MANAGER, StaffRole.MANUFACTURER_STAFF)
            and membership.organization.can_issue
        )


class IsReleaseManager(IsStaff):
    """Only a release manager may put units into circulation or recall a batch."""

    message = "Release manager access is required."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.membership.may_activate


def owns(membership: StaffMembership, organization: Organization | None) -> bool:
    """Object-level check: does this membership own that organization's data?

    A platform admin is deliberately *not* granted ownership here. Admin may
    investigate and restrict through its own endpoints; it does not act as a
    manufacturer, and it never activates on one's behalf.
    """
    if organization is None:
        return False
    return membership.organization_id == organization.id
