"""Append-only audit trail.

Every state transition writes one of these in the same transaction as the change
it describes. Investigations add conclusions; nothing here is ever edited or
deleted, and the application database role should not hold UPDATE or DELETE on
this table in a deployed environment.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.organizations.models import Organization


class AuditAction(models.TextChoices):
    ORGANIZATION_APPROVED = "ORGANIZATION_APPROVED", "Organization approved"
    ORGANIZATION_SUSPENDED = "ORGANIZATION_SUSPENDED", "Organization suspended"
    UNITS_GENERATED = "UNITS_GENERATED", "Units generated"
    MANUFACTURING_RECORDED = "MANUFACTURING_RECORDED", "Manufacturing step recorded"
    UNIT_ACTIVATED = "UNIT_ACTIVATED", "Unit activated"
    UNIT_BLOCKED = "UNIT_BLOCKED", "Unit blocked"
    UNIT_VOIDED = "UNIT_VOIDED", "Unit voided"
    BATCH_RECALLED = "BATCH_RECALLED", "Batch recalled"
    VERIFICATION_COMMITTED = "VERIFICATION_COMMITTED", "Verification committed"
    KEY_REVOKED = "KEY_REVOKED", "Signing key revoked"
    STAFF_MFA_RESET = "STAFF_MFA_RESET", "Staff second factor reset"


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=40, choices=AuditAction.choices)

    #: Null for actions taken by an anonymous consumer session.
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    actor_description = models.CharField(max_length=200, blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )

    unit_id = models.UUIDField(null=True, blank=True)
    batch_id = models.UUIDField(null=True, blank=True)

    reason = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True)

    #: Structured detail. Must never contain a raw token or session credential.
    detail = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_event"
        indexes = [
            models.Index(fields=["organization", "action", "created_at"]),
            models.Index(fields=["unit_id"]),
            models.Index(fields=["request_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.action} at {self.created_at}"
