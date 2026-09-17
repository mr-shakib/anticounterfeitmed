"""URL routing.

Consumer endpoints live under /v1/consumer/. The public landing page is served
by nginx from its own static root and is deliberately not routed here -- it must
have no path to an API, not even an unused one.
"""

from django.contrib import admin
from django.urls import path

from apps.verification import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("v1/consumer/sessions", api.create_session, name="consumer-sessions"),
    path("v1/trust/manifest", api.trust_manifest, name="trust-manifest"),
    path("v1/consumer/verifications/prepare", api.prepare, name="consumer-prepare"),
    path("v1/consumer/verifications/confirm", api.confirm, name="consumer-confirm"),
    path(
        "v1/consumer/operations/<uuid:operation_id>/status",
        api.operation_status,
        name="consumer-operation-status",
    ),
    path("v1/consumer/packages/status", api.package_status, name="consumer-package-status"),
    path("v1/reports", api.create_report, name="consumer-reports"),
]
