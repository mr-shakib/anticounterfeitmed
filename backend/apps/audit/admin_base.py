"""Shared admin bases.

Django's admin grants full edit and delete rights by default, which is wrong for
most of this data. Signed credentials, verification events and audit records are
history: they are read, never rewritten. These bases make that the default so a
new registration has to opt *in* to mutability rather than out of it.

This interface is for platform operators only. It is not the manufacturer
workspace and must never be given to manufacturer staff, because Django admin
has no organization scoping -- a user who can open it sees every manufacturer's
data, which is exactly what docs/01 forbids.
"""

from __future__ import annotations

from django.contrib import admin


class ReadOnlyAdmin(admin.ModelAdmin):
    """Visible and searchable, never editable."""

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class AppendOnlyAdmin(ReadOnlyAdmin):
    """Read-only and undeletable, for records that must survive investigation.

    Investigations add conclusions; they never erase history.
    """

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
