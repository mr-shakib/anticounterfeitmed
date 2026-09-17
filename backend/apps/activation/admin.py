"""Activation jobs and credentials, read-only.

A credential is the exact bytes a manufacturer key signed. Editing one would
make the stored record disagree with its own signature, so the admin cannot.
"""

from django.contrib import admin

from apps.activation.models import ActivationCredential, ActivationJob, ActivationJobItem
from apps.audit.admin_base import ReadOnlyAdmin


@admin.register(ActivationJob)
class ActivationJobAdmin(ReadOnlyAdmin):
    list_display = (
        "approval_id", "batch", "organization", "status",
        "requested_count", "succeeded_count", "failed_count", "finished_at",
    )
    list_filter = ("status", "organization")


@admin.register(ActivationJobItem)
class ActivationJobItemAdmin(ReadOnlyAdmin):
    list_display = ("job", "unit", "succeeded", "failure_reason", "processed_at")
    list_filter = ("succeeded",)


@admin.register(ActivationCredential)
class ActivationCredentialAdmin(ReadOnlyAdmin):
    list_display = (
        "unit", "signing_key", "algorithm", "snapshot_version",
        "credential_digest", "activated_at",
    )
    search_fields = ("credential_digest", "unit__external_reference")
