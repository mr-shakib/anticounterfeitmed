"""Organization and staff administration.

Approving and suspending organizations is a genuine platform-operator function,
so these are editable. Everything downstream of a signature is not.
"""

from django.contrib import admin

from apps.organizations.models import Organization, StaffMembership


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "approval_status", "is_suspended", "created_at")
    list_filter = ("type", "approval_status", "is_suspended")
    search_fields = ("name", "contact_email")
    readonly_fields = ("id", "created_at")


@admin.register(StaffMembership)
class StaffMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_enabled", "mfa_enabled")
    list_filter = ("role", "is_enabled", "mfa_enabled")
    search_fields = ("user__username", "organization__name")
    readonly_fields = ("id", "created_at")
