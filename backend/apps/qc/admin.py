"""Manufacturing records, read-only.

Both timestamps are shown side by side on purpose. These are manufacturer
assertions, not captured factory evidence, and the gap between when a step was
claimed to finish and when someone typed it in is exactly what an investigator
needs to see.
"""

from django.contrib import admin

from apps.audit.admin_base import ReadOnlyAdmin
from apps.qc.models import ManufacturingCompletionEvent


@admin.register(ManufacturingCompletionEvent)
class ManufacturingCompletionEventAdmin(ReadOnlyAdmin):
    list_display = (
        "unit", "step", "completed_at", "recorded_at", "recorded_by",
        "is_manufacturer_asserted", "source_reference",
    )
    list_filter = ("step", "is_manufacturer_asserted")
    search_fields = ("unit__external_reference", "source_reference")
