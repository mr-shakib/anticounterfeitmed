"""Manufacturer-asserted manufacturing completion records.

The printing and QC end is deferred, so these are operational assertions entered
by manufacturer staff -- not automatically captured factory scan evidence. The
distinction is load-bearing, so the model keeps the claimed completion time and
the entry time apart and always records who entered it and from which source
document.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.serialization.models import PackageUnit


class ManufacturingStep(models.TextChoices):
    PRINTED = "PRINTED", "Printed"
    QC_PASSED = "QC_PASSED", "QC passed"
    QC_REJECTED = "QC_REJECTED", "QC rejected"
    COATED = "COATED", "Scratch layer applied"


class ManufacturingCompletionEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    unit = models.ForeignKey(
        PackageUnit, on_delete=models.PROTECT, related_name="manufacturing_events"
    )
    step = models.CharField(max_length=20, choices=ManufacturingStep.choices)

    #: When the physical step actually finished, per the manufacturer.
    completed_at = models.DateTimeField()
    #: When a person typed it in. Deliberately separate from completed_at.
    recorded_at = models.DateTimeField(auto_now_add=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="manufacturing_events"
    )
    source_reference = models.CharField(
        max_length=300,
        help_text="The operational record this assertion came from.",
    )
    reason = models.TextField(blank=True)

    #: Always true in this release. The column exists so a future factory
    #: integration can be distinguished from manual entry without a migration
    #: that rewrites history.
    is_manufacturer_asserted = models.BooleanField(default=True)

    class Meta:
        db_table = "manufacturing_completion_event"
        constraints = [
            # One successful record per step per unit; rejections may repeat.
            models.UniqueConstraint(
                fields=["unit", "step"],
                condition=~models.Q(step=ManufacturingStep.QC_REJECTED),
                name="uniq_completion_per_unit_step",
            )
        ]
        indexes = [models.Index(fields=["unit", "step"])]

    def __str__(self) -> str:
        return f"{self.step} for {self.unit_id}"
