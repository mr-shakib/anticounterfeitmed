"""Products and batches, read-only to the platform operator.

These belong to manufacturers, and their values are frozen into signed
credentials at activation. A platform operator editing a product after issuance
would silently disagree with what was signed, so the admin does not permit it.
"""

from django.contrib import admin

from apps.audit.admin_base import ReadOnlyAdmin
from apps.catalog.models import Batch, Product


@admin.register(Product)
class ProductAdmin(ReadOnlyAdmin):
    list_display = ("brand", "generic", "strength", "dosage_form", "manufacturer")
    list_filter = ("manufacturer", "dosage_form")
    search_fields = ("brand", "generic")


@admin.register(Batch)
class BatchAdmin(ReadOnlyAdmin):
    list_display = (
        "batch_number", "product", "manufactured_on", "expires_on", "is_recalled",
    )
    list_filter = ("is_recalled", "expires_on")
    search_fields = ("batch_number", "product__brand")
