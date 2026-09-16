"""Consumer concern reports and investigation cases.

A report may arrive without a token -- a consumer whose code will not scan still
needs a way to raise a concern -- so external references are accepted instead.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.organizations.models import Organization
from apps.serialization.models import PackageUnit
from apps.verification.models import ConsumerSession


class ReportReason(models.TextChoices):
    CODE_NOT_FOUND = "CODE_NOT_FOUND", "Code not found"
    ALREADY_VERIFIED = "ALREADY_VERIFIED", "Already verified"
    PACKAGING_SUSPICIOUS = "PACKAGING_SUSPICIOUS", "Packaging looks wrong"
    SCAN_FAILED = "SCAN_FAILED", "Cannot scan the code"
    OTHER = "OTHER", "Other"


class ReportStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    IN_REVIEW = "IN_REVIEW", "In review"
    CLOSED = "CLOSED", "Closed"


class Report(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_number = models.CharField(max_length=32, unique=True)

    reason = models.CharField(max_length=30, choices=ReportReason.choices)
    description = models.TextField(blank=True)

    #: Set when the reporter scanned a resolvable code; otherwise the external
    #: reference below is all we have.
    unit = models.ForeignKey(
        PackageUnit, on_delete=models.PROTECT, related_name="reports", null=True, blank=True
    )
    external_reference = models.CharField(max_length=64, blank=True)
    batch_number_text = models.CharField(max_length=100, blank=True)

    reporter_session = models.ForeignKey(
        ConsumerSession, on_delete=models.PROTECT, related_name="reports", null=True, blank=True
    )
    pharmacy_note = models.CharField(
        max_length=300,
        blank=True,
        help_text="Free text. Requires no pharmacy account and creates no sale record.",
    )
    attachment_keys = models.JSONField(default=list, blank=True)

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="reports", null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=ReportStatus.choices, default=ReportStatus.OPEN)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_reports",
        null=True,
        blank=True,
    )
    conclusion = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "report"
        indexes = [models.Index(fields=["status", "reason", "created_at"])]

    def __str__(self) -> str:
        return f"Report {self.case_number} ({self.reason})"
