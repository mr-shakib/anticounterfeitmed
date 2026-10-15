"""The portal's day-to-day work: onboarding, handover, and the batch screens.

Onboarding used to need a shell on the server, a batch's progress was visible
only to the release manager, an activation result vanished with the page, and
one wrong dropdown choice could void a whole batch. These are the guarantees
that replaced each of those.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditAction, AuditEvent
from apps.organizations import mfa
from apps.organizations.models import (
    ApprovalStatus,
    Organization,
    OrganizationType,
    StaffMembership,
    StaffRole,
)
from apps.qc.models import ManufacturingStep
from apps.qc.services import record_completion
from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.serialization.services import create_print_job
from apps.trust.models import KeyPurpose, SigningKey, TrustManifest
from apps.trust.services import provision_signing_key
from tests.test_staff_api import (  # noqa: F401
    PASSWORD,
    make_manufacturer,
    platform_admin,
    sign_in,
)

User = get_user_model()
NEW_PASSWORD = "a-much-better-passphrase-2026"


def _through(unit, user, steps):
    for step in steps:
        record_completion(
            unit=unit,
            step=step,
            completed_at=timezone.now(),
            recorded_by=user,
            source_reference="log",
        )


ALL_STEPS = (ManufacturingStep.PRINTED, ManufacturingStep.QC_PASSED, ManufacturingStep.COATED)


# --- onboarding -------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_admin_adds_a_manufacturer_pending_approval(platform_admin):
    client = APIClient()
    sign_in(client, platform_admin)

    response = client.post(
        reverse("admin-organizations"),
        {"name": "Gamma Pharma", "contact_email": "qa@gamma.example", "contact_phone": "+880"},
        format="json",
    )

    assert response.status_code == 201, response.data
    org = Organization.objects.get(name="Gamma Pharma")
    assert org.type == OrganizationType.MANUFACTURER
    assert org.approval_status == ApprovalStatus.PENDING
    assert response.data["has_signing_key"] is False
    assert AuditEvent.objects.filter(
        action=AuditAction.ORGANIZATION_CREATED, organization=org
    ).exists()

    duplicate = client.post(
        reverse("admin-organizations"),
        {"name": "gamma pharma", "contact_email": "x@y.example"},
        format="json",
    )
    assert duplicate.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_add_organizations_or_staff(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)

    org = client.post(
        reverse("admin-organizations"), {"name": "Rogue", "contact_email": "r@r.example"},
        format="json",
    )
    staff = client.post(
        reverse("admin-memberships"),
        {"organization": str(actor["org"].id), "username": "extra", "role": StaffRole.RELEASE_MANAGER},
        format="json",
    )

    assert org.status_code == 403
    assert staff.status_code == 403
    assert not Organization.objects.filter(name="Rogue").exists()
    assert not User.objects.filter(username="extra").exists()


@pytest.mark.django_db(transaction=True)
def test_approval_gives_a_manufacturer_its_key_and_republishes_the_manifest(platform_admin):
    provision_signing_key(purpose=KeyPurpose.ROOT)
    provision_signing_key(purpose=KeyPurpose.STATUS)
    org = Organization.objects.create(
        type=OrganizationType.MANUFACTURER, name="Delta", contact_email="d@d.example"
    )

    client = APIClient()
    sign_in(client, platform_admin)
    response = client.post(reverse("admin-organization-approve", args=[org.id]), {}, format="json")

    assert response.status_code == 200, response.data
    assert response.data["has_signing_key"] is True
    key = SigningKey.objects.get(organization=org, purpose=KeyPurpose.ACTIVATION)
    manifest = TrustManifest.objects.order_by("-version").first()
    assert manifest is not None and key.key_id.encode() in bytes(manifest.canonical_bytes)
    event = AuditEvent.objects.get(action=AuditAction.ORGANIZATION_APPROVED, organization=org)
    assert event.detail["signing_key_provisioned"] == key.key_id


@pytest.mark.django_db(transaction=True)
def test_approval_does_not_replace_an_existing_key(platform_admin, make_manufacturer):
    provision_signing_key(purpose=KeyPurpose.ROOT)
    target = make_manufacturer("Alpha")  # already holds an activation key
    target["org"].approval_status = ApprovalStatus.PENDING
    target["org"].save(update_fields=["approval_status"])

    client = APIClient()
    sign_in(client, platform_admin)
    client.post(reverse("admin-organization-approve", args=[target["org"].id]), {}, format="json")

    assert SigningKey.objects.filter(
        organization=target["org"], purpose=KeyPurpose.ACTIVATION
    ).count() == 1
    assert not TrustManifest.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_approval_without_a_root_key_approves_nothing(platform_admin):
    """provision-keys.sh refuses once any key exists, so none may come first."""
    org = Organization.objects.create(
        type=OrganizationType.MANUFACTURER, name="Epsilon", contact_email="e@e.example"
    )

    client = APIClient()
    sign_in(client, platform_admin)
    response = client.post(reverse("admin-organization-approve", args=[org.id]), {}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "NO_ROOT_KEY"
    org.refresh_from_db()
    assert org.approval_status == ApprovalStatus.PENDING
    assert not SigningKey.objects.exists()


# --- staff accounts ---------------------------------------------------------


def _add_staff(client, org, username="new-hire", role=StaffRole.MANUFACTURER_STAFF):
    return client.post(
        reverse("admin-memberships"),
        {"organization": str(org.id), "username": username, "role": role},
        format="json",
    )


@pytest.mark.django_db(transaction=True)
def test_admin_adds_staff_with_a_temporary_password_shown_once(platform_admin, make_manufacturer):
    target = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, platform_admin)

    response = _add_staff(client, target["org"])

    assert response.status_code == 201, response.data
    temporary = response.data["temporary_password"]
    assert len(temporary) >= 12
    assert response["Cache-Control"] == "no-store"
    membership = StaffMembership.objects.get(user__username="new-hire")
    assert membership.password_change_required
    assert membership.organization == target["org"]

    # Never echoed again, and never written to the audit trail.
    listing = client.get(reverse("admin-memberships"))
    assert temporary not in str(listing.data)
    event = AuditEvent.objects.get(action=AuditAction.STAFF_CREATED)
    assert temporary not in f"{event.reason} {event.detail}"


@pytest.mark.django_db(transaction=True)
def test_roles_must_fit_the_organization(platform_admin, make_manufacturer):
    target = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, platform_admin)

    admin_at_manufacturer = _add_staff(client, target["org"], role=StaffRole.PLATFORM_ADMIN)
    releaser_at_platform = _add_staff(
        client, platform_admin["org"], username="other", role=StaffRole.RELEASE_MANAGER
    )

    assert admin_at_manufacturer.status_code == 400
    assert releaser_at_platform.status_code == 400
    assert not StaffMembership.objects.filter(user__username__in=["new-hire", "other"]).exists()


@pytest.mark.django_db(transaction=True)
def test_a_taken_username_is_refused(platform_admin, make_manufacturer):
    target = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, platform_admin)

    response = _add_staff(client, target["org"], username=target["user"].get_username().upper())

    assert response.status_code == 409


@pytest.mark.django_db(transaction=True)
def test_a_temporary_password_opens_only_the_password_change(platform_admin, make_manufacturer):
    target = make_manufacturer("Alpha")
    admin_client = APIClient()
    sign_in(admin_client, platform_admin)
    temporary = _add_staff(admin_client, target["org"]).data["temporary_password"]

    client = APIClient()
    login = client.post(
        reverse("staff-login"), {"username": "new-hire", "password": temporary}, format="json"
    )
    assert login.status_code == 200
    assert login.data["password_change_required"] is True
    assert client.get(reverse("staff-batches")).status_code == 403

    wrong = client.post(
        reverse("staff-password"),
        {"current_password": "not-it", "new_password": NEW_PASSWORD},
        format="json",
    )
    weak = client.post(
        reverse("staff-password"),
        {"current_password": temporary, "new_password": "password"},
        format="json",
    )
    assert wrong.status_code == 400
    assert weak.status_code == 400

    changed = client.post(
        reverse("staff-password"),
        {"current_password": temporary, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert changed.status_code == 200, changed.data
    assert changed.data["password_change_required"] is False
    # Same session, no second sign-in needed.
    assert client.get(reverse("staff-batches")).status_code == 200
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_PASSWORD_CHANGED).exists()

    fresh = APIClient()
    assert fresh.post(
        reverse("staff-login"), {"username": "new-hire", "password": temporary}, format="json"
    ).status_code == 401


@pytest.mark.django_db(transaction=True)
def test_an_enrolled_factor_guards_the_password_change(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor, with_mfa=False)

    refused = client.post(
        reverse("staff-password"),
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert refused.status_code == 403

    code = mfa.now_code(actor["membership"].totp_secret)
    client.post(reverse("staff-mfa-verify"), {"code": code}, format="json")
    allowed = client.post(
        reverse("staff-password"),
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert allowed.status_code == 200, allowed.data


@pytest.mark.django_db(transaction=True)
def test_revoking_access_takes_effect_and_can_be_undone(platform_admin, make_manufacturer):
    target = make_manufacturer("Alpha")
    staff_client = APIClient()
    sign_in(staff_client, target)
    assert staff_client.get(reverse("staff-batches")).status_code == 200

    admin_client = APIClient()
    sign_in(admin_client, platform_admin)
    url = reverse("admin-membership-disable", args=[target["membership"].id])
    assert admin_client.post(url, {}, format="json").status_code == 400  # reason required
    revoked = admin_client.post(url, {"reason": "left the company"}, format="json")

    assert revoked.status_code == 200
    assert revoked.data["is_enabled"] is False
    assert staff_client.get(reverse("staff-batches")).status_code == 403
    assert AuditEvent.objects.filter(
        action=AuditAction.STAFF_DISABLED, reason="left the company"
    ).exists()

    restored = admin_client.post(
        reverse("admin-membership-enable", args=[target["membership"].id]), {}, format="json"
    )
    assert restored.status_code == 200
    assert staff_client.get(reverse("staff-batches")).status_code == 200
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_ENABLED).exists()


@pytest.mark.django_db(transaction=True)
def test_an_admin_cannot_revoke_their_own_access(platform_admin):
    client = APIClient()
    sign_in(client, platform_admin)

    response = client.post(
        reverse("admin-membership-disable", args=[platform_admin["membership"].id]),
        {"reason": "oops"},
        format="json",
    )

    assert response.status_code == 409
    platform_admin["membership"].refresh_from_db()
    assert platform_admin["membership"].is_enabled


# --- batch progress and handover ---------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_the_batch_list_shows_where_each_batch_stands(make_manufacturer):
    actor = make_manufacturer("Alpha", role=StaffRole.MANUFACTURER_STAFF)
    result = create_print_job(batch=actor["batch"], count=3)
    units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]
    _through(units[0], actor["user"], ALL_STEPS)
    _through(units[1], actor["user"], ALL_STEPS[:1])

    client = APIClient()
    sign_in(client, actor)
    response = client.get(reverse("staff-batches"))

    assert response.status_code == 200
    progress = response.data[0]["progress"]
    assert progress["units_total"] == 3
    assert progress["units_ready"] == 1
    assert progress["counts_by_lifecycle"] == {
        UnitLifecycle.COVERED: 1,
        UnitLifecycle.PRINTED: 1,
        UnitLifecycle.CREATED: 1,
    }


@pytest.mark.django_db(transaction=True)
def test_units_can_be_searched_by_their_printed_reference(make_manufacturer):
    actor = make_manufacturer("Alpha")
    create_print_job(batch=actor["batch"], count=12)
    batch_number = actor["batch"].batch_number

    client = APIClient()
    sign_in(client, actor)
    url = reverse("staff-batch-units", args=[actor["batch"].id])

    found = client.get(url, {"q": f"{batch_number}-000011"})
    page = client.get(url, {"limit": 5, "offset": 10})

    assert [u["external_reference"] for u in found.data["units"]] == [f"{batch_number}-000011"]
    assert found.data["units_matching"] == 1
    assert page.data["units_matching"] == 12
    assert len(page.data["units"]) == 2
    assert client.get(url, {"limit": "many"}).status_code == 400


@pytest.mark.django_db(transaction=True)
def test_activation_results_outlive_the_page_that_started_them(make_manufacturer):
    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=2)
    units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]
    for unit in units:
        _through(unit, actor["user"], ALL_STEPS)
    units[1].is_blocked = True
    units[1].save(update_fields=["is_blocked"])

    client = APIClient()
    sign_in(client, actor)
    client.post(reverse("staff-activation-jobs"), {"batch": str(actor["batch"].id)}, format="json")

    jobs = client.get(reverse("staff-batch-activation-jobs", args=[actor["batch"].id]))

    assert jobs.status_code == 200
    assert jobs.data[0]["succeeded"] == 1
    assert jobs.data[0]["failed"] == 1
    assert jobs.data[0]["failures"][0]["external_reference"] == units[1].external_reference


@pytest.mark.django_db(transaction=True)
def test_activation_history_is_not_visible_to_another_manufacturer(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")
    client = APIClient()
    sign_in(client, alpha)

    response = client.get(reverse("staff-batch-activation-jobs", args=[beta["batch"].id]))

    assert response.status_code == 404


# --- QC rejection -----------------------------------------------------------


def _reject(client, batch, **extra):
    return client.post(
        reverse("staff-manufacturing-confirmations"),
        {
            "batch": str(batch.id),
            "step": ManufacturingStep.QC_REJECTED,
            "completed_at": timezone.now().isoformat(),
            "source_reference": "QC sheet 14",
            **extra,
        },
        format="json",
    )


@pytest.mark.django_db(transaction=True)
def test_a_rejection_needs_a_reason(make_manufacturer):
    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=2)
    client = APIClient()
    sign_in(client, actor)

    response = _reject(
        client, actor["batch"], external_references=[result.units[0].external_reference]
    )

    assert response.status_code == 400
    assert not PackageUnit.objects.filter(lifecycle=UnitLifecycle.VOID).exists()


@pytest.mark.django_db(transaction=True)
def test_rejecting_a_whole_batch_must_name_it(make_manufacturer):
    actor = make_manufacturer("Alpha")
    create_print_job(batch=actor["batch"], count=3)
    client = APIClient()
    sign_in(client, actor)

    unconfirmed = _reject(client, actor["batch"], reason="ink smeared")
    wrong = _reject(client, actor["batch"], reason="ink smeared", confirm_batch_number="BN-other")
    assert unconfirmed.status_code == 400
    assert wrong.status_code == 400
    assert not PackageUnit.objects.filter(lifecycle=UnitLifecycle.VOID).exists()

    confirmed = _reject(
        client, actor["batch"], reason="ink smeared",
        confirm_batch_number=actor["batch"].batch_number,
    )
    assert confirmed.status_code == 200, confirmed.data
    assert PackageUnit.objects.filter(lifecycle=UnitLifecycle.VOID).count() == 3


@pytest.mark.django_db(transaction=True)
def test_units_are_rejected_by_their_printed_reference(make_manufacturer):
    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=3)
    client = APIClient()
    sign_in(client, actor)

    response = _reject(
        client, actor["batch"], reason="torn",
        external_references=[result.units[1].external_reference],
    )

    assert response.status_code == 200, response.data
    assert response.data["recorded"] == 1
    voided = PackageUnit.objects.get(lifecycle=UnitLifecycle.VOID)
    assert voided.external_reference == result.units[1].external_reference


@pytest.mark.django_db(transaction=True)
def test_one_unknown_reference_records_nothing(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")
    mine = create_print_job(batch=alpha["batch"], count=1)
    theirs = create_print_job(batch=beta["batch"], count=1)
    client = APIClient()
    sign_in(client, alpha)

    response = _reject(
        client, alpha["batch"], reason="torn",
        external_references=[
            mine.units[0].external_reference,
            theirs.units[0].external_reference,
        ],
    )

    assert response.status_code == 400
    assert response.data["unknown"] == [theirs.units[0].external_reference]
    assert not PackageUnit.objects.filter(lifecycle=UnitLifecycle.VOID).exists()


# --- reconciliation ---------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_reconciled_counts_cannot_exceed_the_run(make_manufacturer):
    actor = make_manufacturer("Alpha")
    job = create_print_job(batch=actor["batch"], count=4).print_job
    client = APIClient()
    sign_in(client, actor)
    url = reverse("staff-print-job-reconcile", args=[job.id])

    too_many = client.post(url, {"printed": 5, "rejected": 0}, format="json")
    fine = client.post(url, {"printed": 4, "rejected": 1}, format="json")

    assert too_many.status_code == 400
    assert fine.status_code == 200
