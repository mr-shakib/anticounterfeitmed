"""Signing keys and trust manifests.

Keys are read-only here. Revocation happens through the audited service so that
it is recorded and the next manifest reflects it; flipping a state field by hand
would change behaviour with no audit trail and no manifest update.
"""

from django.contrib import admin

from apps.audit.admin_base import ReadOnlyAdmin
from apps.trust.models import SigningKey, TrustManifest


@admin.register(SigningKey)
class SigningKeyAdmin(ReadOnlyAdmin):
    list_display = ("key_id", "purpose", "organization", "state", "valid_from", "revoked_at")
    list_filter = ("purpose", "state")
    search_fields = ("key_id",)
    # public_key is shown; private_key_reference is a pointer, never material.


@admin.register(TrustManifest)
class TrustManifestAdmin(ReadOnlyAdmin):
    list_display = ("version", "signed_by", "issued_at", "created_at")
