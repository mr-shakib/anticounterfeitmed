"""The admin must not be able to rewrite history or signed data.

Django grants full edit and delete rights by default, so these are asserted
rather than assumed. A future registration that quietly makes a credential or a
verification event editable fails here.

This interface is platform-operator only. Django admin has no organization
scoping, so anyone who can open it sees every manufacturer's data -- which is
why manufacturer staff must never be given access, and why the real workspace in
docs/10 is a separate build.
"""

from __future__ import annotations

import pytest
from django.contrib import admin

from apps.activation.models import ActivationCredential, ActivationJob, ActivationJobItem
from apps.audit.models import AuditEvent
from apps.catalog.models import Batch, Product
from apps.qc.models import ManufacturingCompletionEvent
from apps.serialization.models import PackageUnit, PrintJob
from apps.trust.models import SigningKey, TrustManifest
from apps.verification.models import (
    ConsumerSession,
    SignedReceipt,
    VerificationChallenge,
    VerificationEvent,
    VerificationOperation,
)

#: Nothing here may be created or edited through the admin.
IMMUTABLE_MODELS = [
    ActivationCredential,
    ActivationJob,
    ActivationJobItem,
    AuditEvent,
    Batch,
    ConsumerSession,
    ManufacturingCompletionEvent,
    PackageUnit,
    PrintJob,
    Product,
    SignedReceipt,
    SigningKey,
    TrustManifest,
    VerificationChallenge,
    VerificationEvent,
    VerificationOperation,
]

#: History that must also survive an investigation.
UNDELETABLE_MODELS = [AuditEvent, VerificationEvent]


@pytest.mark.parametrize("model", IMMUTABLE_MODELS, ids=lambda m: m.__name__)
def test_model_is_not_editable_in_admin(model):
    site_admin = admin.site._registry.get(model)
    assert site_admin is not None, f"{model.__name__} is not registered"
    assert not site_admin.has_add_permission(None), f"{model.__name__} is addable"
    assert not site_admin.has_change_permission(None), f"{model.__name__} is editable"


@pytest.mark.parametrize("model", UNDELETABLE_MODELS, ids=lambda m: m.__name__)
def test_history_cannot_be_deleted_in_admin(model):
    site_admin = admin.site._registry[model]
    assert not site_admin.has_delete_permission(None), f"{model.__name__} is deletable"


class _SuperuserRequest:
    """Minimal stand-in: Django's default permission checks read request.user."""

    class _User:
        is_active = True
        is_superuser = True

        def has_perm(self, perm, obj=None):
            return True

        def has_module_perms(self, app_label):
            return True

    user = _User()


def test_organization_remains_editable():
    """Approving and suspending an organization is a real operator function."""
    from apps.organizations.models import Organization

    site_admin = admin.site._registry[Organization]
    assert site_admin.has_change_permission(_SuperuserRequest())


def test_reported_facts_are_read_only_but_triage_is_not():
    """A case can be assigned and concluded; what was reported cannot change."""
    from apps.reports.models import Report

    site_admin = admin.site._registry[Report]
    assert site_admin.has_change_permission(_SuperuserRequest())
    for field in ("case_number", "reason", "description", "reporter_session"):
        assert field in site_admin.readonly_fields, f"{field} must not be editable"
    for field in ("status", "assigned_to", "conclusion"):
        assert field not in site_admin.readonly_fields, f"{field} should be editable"


def test_raw_token_is_not_searchable_or_displayed():
    """No admin surface may expose or search a token."""
    for model, site_admin in admin.site._registry.items():
        for attr in ("list_display", "search_fields", "readonly_fields"):
            fields = getattr(site_admin, attr, ()) or ()
            for field in fields:
                assert "token_sha256" not in str(field) or attr == "readonly_fields", (
                    f"{model.__name__}.{attr} exposes {field}"
                )
                assert "credential_sha256" not in str(field), (
                    f"{model.__name__}.{attr} exposes a session credential digest"
                )
