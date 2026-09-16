"""Organizations and staff access.

Every staff action in the system is scoped to an organization. Suspension lives
here rather than on the unit because it is a restriction that overrides an
otherwise positive verification result.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class OrganizationType(models.TextChoices):
    PLATFORM = "PLATFORM", "Platform operator"
    MANUFACTURER = "MANUFACTURER", "Manufacturer"


class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending approval"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=OrganizationType.choices)
    name = models.CharField(max_length=200)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)

    approval_status = models.CharField(
        max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Suspension is deliberately separate from approval: an approved issuer can
    # be suspended without losing its approval history.
    is_suspended = models.BooleanField(default=False)
    suspended_at = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organization"
        constraints = [
            models.UniqueConstraint(fields=["name"], name="uniq_organization_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    @property
    def can_issue(self) -> bool:
        """True when this organization may issue and activate units."""
        return (
            self.type == OrganizationType.MANUFACTURER
            and self.approval_status == ApprovalStatus.APPROVED
            and not self.is_suspended
        )


class StaffRole(models.TextChoices):
    PLATFORM_ADMIN = "PLATFORM_ADMIN", "Platform admin"
    RELEASE_MANAGER = "RELEASE_MANAGER", "Manufacturer release manager"
    MANUFACTURER_STAFF = "MANUFACTURER_STAFF", "Manufacturer staff"


class StaffMembership(models.Model):
    """Binds a user to an organization with one role.

    Activation is restricted to RELEASE_MANAGER; ordinary staff can prepare
    everything up to that point but cannot release units.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=32, choices=StaffRole.choices)
    is_enabled = models.BooleanField(default=True)
    mfa_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    disabled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "staff_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"], name="uniq_membership_user_org"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} as {self.role}"

    @property
    def may_activate(self) -> bool:
        return (
            self.is_enabled
            and self.role == StaffRole.RELEASE_MANAGER
            and self.organization.can_issue
        )
