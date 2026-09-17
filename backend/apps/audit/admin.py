"""The audit trail.

Append-only by design: investigations add conclusions, they never erase history.
"""

from django.contrib import admin

from apps.audit.admin_base import AppendOnlyAdmin
from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(AppendOnlyAdmin):
    list_display = (
        "created_at", "action", "organization", "actor_user",
        "actor_description", "unit_id", "request_id",
    )
    list_filter = ("action", "organization")
    search_fields = ("request_id", "reason", "actor_description")
    date_hierarchy = "created_at"
