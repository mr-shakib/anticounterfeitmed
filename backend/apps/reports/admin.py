"""Concern reports and the investigation queue.

Status, assignment and conclusion are editable because triaging a case is the
work. The reported facts are not.
"""

from django.contrib import admin

from apps.reports.models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("case_number", "reason", "status", "organization", "assigned_to", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("case_number", "external_reference", "batch_number_text")
    readonly_fields = (
        "id", "case_number", "reason", "description", "unit", "external_reference",
        "batch_number_text", "reporter_session", "pharmacy_note", "attachment_keys",
        "created_at",
    )
