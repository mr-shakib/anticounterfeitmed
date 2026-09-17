"""Units and print jobs, read-only.

The token digest is shown; the raw token does not exist anywhere to show. A
unit's lifecycle is changed through the audited service layer, never by editing
a row here -- that is how REDEEMED stays permanent.
"""

from django.contrib import admin

from apps.audit.admin_base import ReadOnlyAdmin
from apps.serialization.models import PackageUnit, PrintJob


@admin.register(PrintJob)
class PrintJobAdmin(ReadOnlyAdmin):
    list_display = (
        "id", "batch", "manufacturer", "planned_count", "issued_count", "status",
    )
    list_filter = ("status", "manufacturer")


@admin.register(PackageUnit)
class PackageUnitAdmin(ReadOnlyAdmin):
    list_display = (
        "external_reference", "batch", "lifecycle", "is_blocked",
        "activated_at", "redeemed_at",
    )
    list_filter = ("lifecycle", "is_blocked", "batch")
    search_fields = ("external_reference",)
    # token_sha256 is deliberately absent from search: a digest is not a
    # lookup key an operator should be pasting around.
