"""URL routing.

Three surfaces, kept deliberately separate:

* ``/v1/consumer/`` -- the mobile app. Requires a session *and* app attestation.
* ``/v1/staff/``    -- the staff portal. Requires a staff session, MFA for
  privileged roles, and is scoped to the caller's own organization.
* ``/admin/``       -- Django admin, platform operators only.

A consumer credential is never authority on a staff route, and a staff session
is never a substitute for app attestation on a consumer route.

The public landing page is served by nginx from its own static root and is
deliberately not routed here.
"""

from django.contrib import admin
from django.urls import path

from apps.activation import api as activation_api
from apps.audit import api as admin_api
from apps.catalog import api as catalog_api
from apps.organizations import api as staff_api
from apps.qc import api as qc_api
from apps.serialization import api as serialization_api
from apps.verification import api as consumer_api

consumer_patterns = [
    path("v1/consumer/sessions", consumer_api.create_session, name="consumer-sessions"),
    path("v1/trust/manifest", consumer_api.trust_manifest, name="trust-manifest"),
    path("v1/consumer/verifications/prepare", consumer_api.prepare, name="consumer-prepare"),
    path("v1/consumer/verifications/confirm", consumer_api.confirm, name="consumer-confirm"),
    path(
        "v1/consumer/operations/<uuid:operation_id>/status",
        consumer_api.operation_status,
        name="consumer-operation-status",
    ),
    path(
        "v1/consumer/packages/status",
        consumer_api.package_status,
        name="consumer-package-status",
    ),
    path("v1/reports", consumer_api.create_report, name="consumer-reports"),
]

staff_auth_patterns = [
    path("v1/staff/login", staff_api.staff_login, name="staff-login"),
    path("v1/staff/logout", staff_api.staff_logout, name="staff-logout"),
    path("v1/staff/me", staff_api.whoami, name="staff-me"),
    path("v1/staff/mfa/enroll", staff_api.mfa_enroll, name="staff-mfa-enroll"),
    path("v1/staff/mfa/confirm", staff_api.mfa_confirm, name="staff-mfa-confirm"),
    path("v1/staff/mfa/verify", staff_api.mfa_verify, name="staff-mfa-verify"),
    path("v1/staff/mfa/disable", staff_api.mfa_disable, name="staff-mfa-disable"),
    path("v1/admin/memberships", staff_api.list_memberships, name="admin-memberships"),
    path(
        "v1/admin/memberships/<uuid:membership_id>/reset-mfa",
        staff_api.reset_membership_mfa,
        name="admin-membership-reset-mfa",
    ),
]

manufacturer_patterns = [
    path("v1/staff/products", catalog_api.products, name="staff-products"),
    path("v1/staff/batches", catalog_api.batches, name="staff-batches"),
    path("v1/staff/batches/<uuid:batch_id>", catalog_api.batch_detail, name="staff-batch"),
    path(
        "v1/staff/batches/<uuid:batch_id>/units",
        serialization_api.batch_units,
        name="staff-batch-units",
    ),
    path("v1/staff/print-jobs", serialization_api.print_jobs, name="staff-print-jobs"),
    path(
        "v1/staff/manufacturing-confirmations",
        qc_api.manufacturing_confirmations,
        name="staff-manufacturing-confirmations",
    ),
    path(
        "v1/staff/units/<uuid:unit_id>/readiness",
        qc_api.unit_readiness,
        name="staff-unit-readiness",
    ),
    path(
        "v1/staff/activation-jobs",
        activation_api.activation_jobs,
        name="staff-activation-jobs",
    ),
    path(
        "v1/staff/activation-jobs/<uuid:job_id>",
        activation_api.activation_job_detail,
        name="staff-activation-job",
    ),
    path(
        "v1/staff/activation-jobs/<uuid:job_id>/retry",
        activation_api.activation_job_retry,
        name="staff-activation-job-retry",
    ),
    path(
        "v1/staff/batches/<uuid:batch_id>/recall",
        activation_api.recall_batch,
        name="staff-batch-recall",
    ),
    path(
        "v1/staff/units/<uuid:unit_id>/block",
        activation_api.block_unit,
        name="staff-unit-block",
    ),
]

platform_admin_patterns = [
    path("v1/admin/organizations", admin_api.organizations, name="admin-organizations"),
    path(
        "v1/admin/organizations/<uuid:organization_id>/approve",
        admin_api.approve_organization,
        name="admin-organization-approve",
    ),
    path(
        "v1/admin/organizations/<uuid:organization_id>/suspend",
        admin_api.suspend_organization,
        name="admin-organization-suspend",
    ),
    path("v1/admin/audit", admin_api.audit_search, name="admin-audit"),
    path("v1/admin/reports", admin_api.investigation_queue, name="admin-reports"),
    path(
        "v1/admin/reports/<str:case_number>/conclude",
        admin_api.conclude_report,
        name="admin-report-conclude",
    ),
    path("v1/admin/dashboard", admin_api.operational_dashboard, name="admin-dashboard"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    *consumer_patterns,
    *staff_auth_patterns,
    *manufacturer_patterns,
    *platform_admin_patterns,
]
