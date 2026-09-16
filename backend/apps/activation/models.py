"""Activation: approvals, bulk jobs, and the signed credential per unit.

Activation is the only point at which a manufacturer key signs anything. A unit
becomes ACTIVE and its credential becomes available in the same transaction, so
a unit can never be active without a valid credential.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.catalog.models import Batch
from apps.organizations.models import Organization
from apps.serialization.models import PackageUnit
from apps.trust.models import SigningKey


class ActivationJobStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    COMPLETED_WITH_FAILURES = "COMPLETED_WITH_FAILURES", "Completed with failures"
    FAILED = "FAILED", "Failed"


class ActivationJob(models.Model):
    """A tracked bulk activation.

    Per-unit results are recorded so a partially failed run is never reported as
    a fully activated batch. Retries cover only the failed units.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="activation_jobs"
    )
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="activation_jobs")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="activation_jobs"
    )
    approval_id = models.CharField(max_length=80, unique=True)

    status = models.CharField(
        max_length=30, choices=ActivationJobStatus.choices, default=ActivationJobStatus.PENDING
    )
    requested_count = models.PositiveIntegerField(default=0)
    succeeded_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "activation_job"
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self) -> str:
        return f"Activation job {self.id} ({self.status})"


class ActivationJobItem(models.Model):
    """The outcome for one unit inside a bulk activation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(ActivationJob, on_delete=models.CASCADE, related_name="items")
    unit = models.ForeignKey(
        PackageUnit, on_delete=models.PROTECT, related_name="activation_items"
    )
    succeeded = models.BooleanField(default=False)
    failure_reason = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "activation_job_item"
        constraints = [
            models.UniqueConstraint(fields=["job", "unit"], name="uniq_job_item_unit")
        ]


class ActivationCredential(models.Model):
    """The immutable ML-DSA-signed record for one unit.

    ``canonical_bytes`` is exactly what was signed and exactly what is sent to
    the app. It is never rebuilt from the columns around it, because a
    re-serialisation is not guaranteed to reproduce the signed bytes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    unit = models.OneToOneField(
        PackageUnit, on_delete=models.PROTECT, related_name="activation_credential"
    )
    job = models.ForeignKey(
        ActivationJob,
        on_delete=models.PROTECT,
        related_name="credentials",
        null=True,
        blank=True,
    )

    canonical_bytes = models.BinaryField()
    signature = models.BinaryField(max_length=4096)
    signing_key = models.ForeignKey(
        SigningKey, on_delete=models.PROTECT, related_name="credentials"
    )
    algorithm = models.CharField(max_length=20, default="ML-DSA-65")

    #: SHA-256 over canonical_bytes; status envelopes cite this so a status
    #: statement is bound to the exact credential the app previewed.
    credential_digest = models.CharField(max_length=64)

    #: The unit version this credential was issued against.
    snapshot_version = models.PositiveIntegerField()

    activated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activation_credential"
        indexes = [models.Index(fields=["credential_digest"])]

    def __str__(self) -> str:
        return f"Credential for unit {self.unit_id}"
