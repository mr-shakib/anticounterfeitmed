"""Verification history, read-only and undeletable.

A verification event is the record that a redemption happened. It is permanent:
nothing in this interface can reset a redeemed unit or remove the evidence that
a check occurred.
"""

from django.contrib import admin

from apps.audit.admin_base import AppendOnlyAdmin, ReadOnlyAdmin
from apps.verification.models import (
    ConsumerSession,
    SignedReceipt,
    VerificationChallenge,
    VerificationEvent,
    VerificationOperation,
)


@admin.register(VerificationEvent)
class VerificationEventAdmin(AppendOnlyAdmin):
    list_display = ("unit", "event_type", "server_time", "session")
    list_filter = ("event_type",)
    search_fields = ("unit__external_reference",)


@admin.register(VerificationOperation)
class VerificationOperationAdmin(ReadOnlyAdmin):
    list_display = ("id", "session", "unit", "outcome", "receipt_ready", "created_at")
    list_filter = ("outcome", "receipt_ready")


@admin.register(SignedReceipt)
class SignedReceiptAdmin(ReadOnlyAdmin):
    list_display = ("event", "status", "attempts", "signed_at", "last_error")
    list_filter = ("status",)


@admin.register(ConsumerSession)
class ConsumerSessionAdmin(ReadOnlyAdmin):
    # The credential digest is stored, never the credential. Nothing here
    # identifies a person: a session is an installation.
    list_display = ("id", "app_id", "created_at", "expires_at", "revoked_at", "last_seen_at")
    list_filter = ("app_id",)


@admin.register(VerificationChallenge)
class VerificationChallengeAdmin(ReadOnlyAdmin):
    list_display = ("id", "unit", "session", "credential_version", "expires_at", "consumed_at")
