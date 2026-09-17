"""Staff authorization.

Two rules run through everything here.

Scoping is by membership, never by anything the caller sends. A request never
names the organization it is acting for: that comes from the authenticated
membership, so a manufacturer cannot reach another's data by changing a field.

Privileged roles must hold a second factor, and the check is on the *session*
having completed it, not merely on the account having it enabled.
"""

from __future__ import annotations

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


def session_mfa_ok(request, membership: StaffMembership) -> bool:
    """True when this session has cleared MFA for this membership."""
    if not membership.is_privileged:
        return True
    if not membership.mfa_satisfied:
        return False
    return str(request.session.get(MFA_SESSION_KEY, "")) == str(membership.id)


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
