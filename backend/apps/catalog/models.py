"""Products and batches.

The values here are what a manufacturer maintains day to day. The moment a unit
is activated, the relevant fields are frozen into a signed credential -- editing
a product afterwards must never change what was already issued.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import Organization


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manufacturer = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="products"
    )

    brand = models.CharField(max_length=200)
    generic = models.CharField(max_length=200)
    strength = models.CharField(max_length=100)
    dosage_form = models.CharField(max_length=100)
    pack_description = models.CharField(
        max_length=200,
        help_text="The unit as sold, e.g. 'Strip of 10 tablets'.",
    )
    registration_reference = models.CharField(max_length=100, blank=True)

    reference_image_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="Object storage key. Illustrative unless its digest is signed.",
    )
    reference_image_sha256 = models.BinaryField(
        max_length=32,
        null=True,
        blank=True,
        help_text="Set only when the image is presented as authenticated (decision D7).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product"
        indexes = [models.Index(fields=["manufacturer", "brand"])]

    def __str__(self) -> str:
        return f"{self.brand} {self.strength} ({self.generic})"


class Batch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=100)

    manufactured_on = models.DateField()
    # Never nullable, and never inferred. If a label shows only month and year,
    # the manufacturer supplies the intended final valid date (decision D2).
    expires_on = models.DateField()

    planned_unit_count = models.PositiveIntegerField()

    is_recalled = models.BooleanField(default=False)
    recalled_at = models.DateTimeField(null=True, blank=True)
    recall_notice = models.TextField(blank=True)
    recall_contact = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "batch"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "batch_number"], name="uniq_batch_per_product"
            ),
            models.CheckConstraint(
                condition=models.Q(expires_on__gt=models.F("manufactured_on")),
                name="batch_expiry_after_manufacture",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.brand} batch {self.batch_number}"

    def clean(self) -> None:
        if self.expires_on and self.manufactured_on and self.expires_on <= self.manufactured_on:
            raise ValidationError({"expires_on": "Expiry must be after the manufacturing date."})

    @property
    def manufacturer(self) -> Organization:
        return self.product.manufacturer
