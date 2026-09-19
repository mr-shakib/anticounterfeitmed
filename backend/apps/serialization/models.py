"""Serialization: print jobs and package units.

A package unit is one physical strip. One strip carries exactly one QR, so a
1,000-strip run produces 1,000 units and 1,000 distinct tokens (decision D1).
A strip that is later cut apart is no longer the unit this code authenticates.

Only ``token_sha256`` is stored. The raw token exists in the print-generation
path and in transient request memory, and nowhere else.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.catalog.models import Batch
from apps.organizations.models import Organization


class UnitLifecycle(models.TextChoices):
    """The states from docs/04. Restrictions are tracked separately."""

    CREATED = "CREATED", "Created"
    PRINTED = "PRINTED", "Printed"
    QC_PASSED = "QC_PASSED", "QC passed"
    COVERED = "COVERED", "Coated"
    ACTIVE = "ACTIVE", "Active"
    REDEEMED = "REDEEMED", "Redeemed"
    VOID = "VOID", "Void"


#: The only transitions the system may perform. REDEEMED and VOID are terminal;
#: nothing returns a redeemed unit to ACTIVE.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    UnitLifecycle.CREATED: frozenset({UnitLifecycle.PRINTED, UnitLifecycle.VOID}),
    UnitLifecycle.PRINTED: frozenset({UnitLifecycle.QC_PASSED, UnitLifecycle.VOID}),
    UnitLifecycle.QC_PASSED: frozenset({UnitLifecycle.COVERED, UnitLifecycle.VOID}),
    UnitLifecycle.COVERED: frozenset({UnitLifecycle.ACTIVE, UnitLifecycle.VOID}),
    UnitLifecycle.ACTIVE: frozenset({UnitLifecycle.REDEEMED}),
    UnitLifecycle.REDEEMED: frozenset(),
    UnitLifecycle.VOID: frozenset(),
}


class PrintJobStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    GENERATED = "GENERATED", "Serials generated"
    EXPORTED = "EXPORTED", "Label export downloaded"
    RECONCILED = "RECONCILED", "Quantities reconciled"
    CANCELLED = "CANCELLED", "Cancelled"


class PrintJob(models.Model):
    """A serialization run for one batch.

    Printing happens outside the platform. This record exists so quantities can
    be reconciled and so the controlled label export can be deleted on schedule.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manufacturer = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="print_jobs"
    )
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="print_jobs")

    planned_count = models.PositiveIntegerField()
    issued_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=PrintJobStatus.choices, default=PrintJobStatus.DRAFT
    )

    export_object_key = models.CharField(max_length=500, blank=True)

    #: The label export, encrypted at rest.
    #:
    #: The SRS keeps encrypted print artifacts until a job is reconciled and
    #: then deletes them within 24 hours. That is what this is: it lets a
    #: manufacturer come back for the codes they have not printed yet, without
    #: keeping raw tokens indefinitely. The plaintext never enters another
    #: column, and the ciphertext is removed on the schedule below.
    export_ciphertext = models.BinaryField(null=True, blank=True)

    #: When the export stops being retrievable. Set on creation to a maximum
    #: lifetime, and shortened to 24 hours when the job is reconciled.
    export_expires_at = models.DateTimeField(null=True, blank=True)

    export_deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Export must be deleted within 24 hours of reconciliation.",
    )

    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_printed = models.PositiveIntegerField(default=0)
    reconciled_rejected = models.PositiveIntegerField(default=0)

    created_by = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "print_job"
        indexes = [models.Index(fields=["manufacturer", "status"])]

    def __str__(self) -> str:
        return f"Print job {self.id} for {self.batch}"

    def export_available(self, now) -> bool:
        """Whether the labels can still be retrieved."""
        return bool(
            self.export_ciphertext
            and self.export_expires_at
            and self.export_expires_at > now
            and self.export_deleted_at is None
        )


class PackageUnit(models.Model):
    """One strip, one QR, one token."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="units")
    print_job = models.ForeignKey(
        PrintJob, on_delete=models.PROTECT, related_name="units", null=True, blank=True
    )

    #: Human-readable reference printed alongside the QR. It identifies a unit
    #: for reconciliation and support, and can never redeem one.
    external_reference = models.CharField(max_length=64)

    #: SHA-256 of the raw token. The raw token is never stored.
    token_sha256 = models.BinaryField(max_length=32)

    lifecycle = models.CharField(
        max_length=20, choices=UnitLifecycle.choices, default=UnitLifecycle.CREATED
    )

    # Restrictions, kept separate from lifecycle so a redeemed unit can also be
    # blocked and both facts stay visible.
    is_blocked = models.BooleanField(default=False)
    blocked_at = models.DateTimeField(null=True, blank=True)
    blocked_reason = models.TextField(blank=True)

    #: Bumped whenever the signed snapshot changes, so a challenge issued
    #: against one credential version cannot be redeemed against another.
    version = models.PositiveIntegerField(default=1)

    activated_at = models.DateTimeField(null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "package_unit"
        constraints = [
            models.UniqueConstraint(fields=["token_sha256"], name="uniq_unit_token_sha256"),
            models.UniqueConstraint(
                fields=["batch", "external_reference"], name="uniq_unit_external_reference"
            ),
        ]
        indexes = [
            models.Index(fields=["batch", "lifecycle"]),
        ]

    def __str__(self) -> str:
        return f"Unit {self.external_reference} ({self.lifecycle})"

    @property
    def manufacturer(self) -> Organization:
        return self.batch.product.manufacturer

    def can_transition_to(self, target: str) -> bool:
        return target in ALLOWED_TRANSITIONS[self.lifecycle]
