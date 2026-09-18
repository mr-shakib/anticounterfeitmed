"""Staff API: authentication, MFA, and organization scoping.

The isolation tests here are milestone 2's gate expressed at the HTTP layer.
Proving it in the service layer was necessary but not sufficient: the endpoints
are what an attacker actually reaches.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Batch, Product
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
from apps.trust.models import KeyPurpose
from apps.trust.services import provision_signing_key

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def make_manufacturer(db):
    def build(name: str, role: str = StaffRole.RELEASE_MANAGER):
        org = Organization.objects.create(
            type=OrganizationType.MANUFACTURER,
            name=name,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=timezone.now(),
        )
        user = User.objects.create_user(username=f"user-{name}".replace(" ", "-"))
        user.set_password(PASSWORD)
        user.save()
        membership = StaffMembership.objects.create(
            user=user,
            organization=org,
            role=role,
            mfa_enabled=True,
            totp_secret=mfa.new_secret(),
            mfa_confirmed_at=timezone.now(),
        )
        product = Product.objects.create(
            manufacturer=org, brand=f"Brand-{name}", generic="Paracetamol",
            strength="500 mg", dosage_form="Tablet", pack_description="Strip of 10",
        )
        batch = Batch.objects.create(
            product=product, batch_number=f"BN-{org.id.hex[:6]}",
            manufactured_on=date.today() - timedelta(days=10),
            expires_on=date.today() + timedelta(days=400), planned_unit_count=10,
        )
        provision_signing_key(purpose=KeyPurpose.ACTIVATION, organization=org)
        return {"org": org, "user": user, "membership": membership,
                "product": product, "batch": batch}

    return build


@pytest.fixture
def platform_admin(db):
    org = Organization.objects.create(
        type=OrganizationType.PLATFORM, name="Platform",
        approval_status=ApprovalStatus.APPROVED, approved_at=timezone.now(),
    )
    user = User.objects.create_user(username="admin-user")
    user.set_password(PASSWORD)
    user.save()
    membership = StaffMembership.objects.create(
        user=user, organization=org, role=StaffRole.PLATFORM_ADMIN,
        mfa_enabled=True, totp_secret=mfa.new_secret(), mfa_confirmed_at=timezone.now(),
    )
    return {"org": org, "user": user, "membership": membership}


def sign_in(client: APIClient, actor: dict, with_mfa: bool = True):
    response = client.post(
        reverse("staff-login"),
        {"username": actor["user"].get_username(), "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.data
    if with_mfa:
        code = mfa.now_code(actor["membership"].totp_secret)
        verified = client.post(reverse("staff-mfa-verify"), {"code": code}, format="json")
        assert verified.status_code == 200, verified.data
    return response


# --- authentication ---------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_login_requires_valid_credentials(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    response = client.post(
        reverse("staff-login"),
        {"username": actor["user"].get_username(), "password": "wrong"},
        format="json",
    )
    assert response.status_code == 401
    assert response.data["code"] == "INVALID_CREDENTIALS"


@pytest.mark.django_db(transaction=True)
def test_anonymous_cannot_reach_staff_endpoints(make_manufacturer):
    make_manufacturer("Alpha")
    client = APIClient()
    for url in [reverse("staff-products"), reverse("staff-batches"),
                reverse("admin-organizations"), reverse("staff-me")]:
        assert client.get(url).status_code in (401, 403), url


@pytest.mark.django_db(transaction=True)
def test_password_alone_does_not_grant_privileged_access(make_manufacturer):
    """A stolen password must not be enough for a release manager."""
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor, with_mfa=False)

    # Authenticated, but the session has not cleared the second factor.
    assert client.get(reverse("staff-products")).status_code == 403

    sign_in(client, actor, with_mfa=True)
    assert client.get(reverse("staff-products")).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_wrong_totp_code_is_refused(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor, with_mfa=False)
    response = client.post(reverse("staff-mfa-verify"), {"code": "000000"}, format="json")
    assert response.status_code == 400
    assert response.data["code"] == "INVALID_CODE"


@pytest.mark.django_db(transaction=True)
def test_disabled_membership_cannot_sign_in(make_manufacturer):
    actor = make_manufacturer("Alpha")
    actor["membership"].is_enabled = False
    actor["membership"].save(update_fields=["is_enabled"])

    client = APIClient()
    response = client.post(
        reverse("staff-login"),
        {"username": actor["user"].get_username(), "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 403
    assert response.data["code"] == "NO_MEMBERSHIP"


# --- the isolation gate -----------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_manufacturer_sees_only_its_own_catalogue(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")

    client = APIClient()
    sign_in(client, alpha)

    brands = {p["brand"] for p in client.get(reverse("staff-products")).data}
    assert brands == {"Brand-Alpha"}

    numbers = {b["batch_number"] for b in client.get(reverse("staff-batches")).data}
    assert numbers == {alpha["batch"].batch_number}
    assert beta["batch"].batch_number not in numbers


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_read_another_batch_by_id(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")

    client = APIClient()
    sign_in(client, alpha)

    response = client.get(reverse("staff-batch", args=[beta["batch"].id]))
    # 404, not 403: a 403 would confirm the id is real.
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_serialise_into_another_batch(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")

    client = APIClient()
    sign_in(client, alpha)

    response = client.post(
        reverse("staff-print-jobs"),
        {"batch": str(beta["batch"].id), "count": 5},
        format="json",
    )
    assert response.status_code == 404
    assert not PackageUnit.objects.filter(batch=beta["batch"]).exists()


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_activate_another_batch(make_manufacturer):
    """Milestone 2's gate, at the HTTP layer."""
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")

    result = create_print_job(batch=beta["batch"], count=1)
    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)
    for step in (ManufacturingStep.PRINTED, ManufacturingStep.QC_PASSED,
                 ManufacturingStep.COATED):
        record_completion(unit=unit, step=step, completed_at=timezone.now(),
                          recorded_by=beta["user"], source_reference="log")

    client = APIClient()
    sign_in(client, alpha)
    response = client.post(
        reverse("staff-activation-jobs"),
        {"batch": str(beta["batch"].id), "unit_ids": [str(unit.id)]},
        format="json",
    )
    assert response.status_code == 404

    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.COVERED, "Beta's unit must be untouched"


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_record_manufacturing_for_another(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")

    result = create_print_job(batch=beta["batch"], count=1)
    unit_id = result.units[0].unit_id

    client = APIClient()
    sign_in(client, alpha)
    response = client.post(
        reverse("staff-manufacturing-confirmations"),
        {
            "unit_ids": [str(unit_id)],
            "step": ManufacturingStep.PRINTED,
            "completed_at": timezone.now().isoformat(),
            "source_reference": "forged-log",
        },
        format="json",
    )
    assert response.status_code == 404
    assert PackageUnit.objects.get(pk=unit_id).lifecycle == UnitLifecycle.CREATED


@pytest.mark.django_db(transaction=True)
def test_mixed_unit_list_is_refused_entirely(make_manufacturer):
    """A list mixing own and foreign units records nothing at all."""
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")

    mine = create_print_job(batch=alpha["batch"], count=1).units[0]
    theirs = create_print_job(batch=beta["batch"], count=1).units[0]

    client = APIClient()
    sign_in(client, alpha)
    response = client.post(
        reverse("staff-manufacturing-confirmations"),
        {
            "unit_ids": [str(mine.unit_id), str(theirs.unit_id)],
            "step": ManufacturingStep.PRINTED,
            "completed_at": timezone.now().isoformat(),
            "source_reference": "log",
        },
        format="json",
    )
    assert response.status_code == 404
    # Not even the caller's own unit advanced.
    assert PackageUnit.objects.get(pk=mine.unit_id).lifecycle == UnitLifecycle.CREATED


# --- role boundaries --------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_ordinary_staff_cannot_activate(make_manufacturer):
    actor = make_manufacturer("Alpha", role=StaffRole.MANUFACTURER_STAFF)
    result = create_print_job(batch=actor["batch"], count=1)

    client = APIClient()
    sign_in(client, actor, with_mfa=False)  # not a privileged role

    response = client.post(
        reverse("staff-activation-jobs"),
        {"batch": str(actor["batch"].id), "unit_ids": [str(result.units[0].unit_id)]},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_reach_admin_endpoints(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)

    for url in [reverse("admin-organizations"), reverse("admin-audit"),
                reverse("admin-dashboard"), reverse("admin-reports")]:
        assert client.get(url).status_code == 403, url


@pytest.mark.django_db(transaction=True)
def test_admin_cannot_use_manufacturer_endpoints(platform_admin, make_manufacturer):
    """Admin investigates and restricts; it does not act as a manufacturer."""
    make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, platform_admin)

    assert client.get(reverse("staff-products")).status_code == 403
    assert client.post(
        reverse("staff-print-jobs"), {"batch": str(make_manufacturer("Gamma")["batch"].id),
                                      "count": 1}, format="json"
    ).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_admin_can_approve_and_suspend(platform_admin, make_manufacturer):
    target = make_manufacturer("Alpha")
    target["org"].approval_status = ApprovalStatus.PENDING
    target["org"].save(update_fields=["approval_status"])

    client = APIClient()
    sign_in(client, platform_admin)

    approved = client.post(
        reverse("admin-organization-approve", args=[target["org"].id]), {}, format="json"
    )
    assert approved.status_code == 200
    assert approved.data["approval_status"] == ApprovalStatus.APPROVED

    suspended = client.post(
        reverse("admin-organization-suspend", args=[target["org"].id]),
        {"reason": "Under investigation"},
        format="json",
    )
    assert suspended.status_code == 200
    assert suspended.data["is_suspended"] is True

    target["org"].refresh_from_db()
    assert target["org"].is_suspended


@pytest.mark.django_db(transaction=True)
def test_suspended_manufacturer_loses_access(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)
    assert client.get(reverse("staff-products")).status_code == 200

    actor["org"].is_suspended = True
    actor["org"].save(update_fields=["is_suspended"])

    assert client.get(reverse("staff-products")).status_code == 403


# --- the export -------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_label_export_is_returned_once_and_never_again(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)

    response = client.post(
        reverse("staff-print-jobs"),
        {"batch": str(actor["batch"].id), "count": 3},
        format="json",
    )
    assert response.status_code == 201
    export = response.data["label_export"]
    assert len(export) == 3
    assert all(e["qr_url"].startswith("https://anticounterfeitmed.com/#v=1&t=") for e in export)

    # Nothing else exposes a token: the unit listing has no way to return one.
    units = client.get(reverse("staff-batch-units", args=[actor["batch"].id]))
    assert units.status_code == 200
    body = str(units.data)
    for entry in export:
        token = entry["qr_url"].split("t=")[1]
        assert token not in body, "a token was retrievable after issuance"


@pytest.mark.django_db(transaction=True)
def test_activation_reports_partial_failure_honestly(make_manufacturer):
    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=2)
    units = [PackageUnit.objects.get(pk=u.unit_id) for u in result.units]

    # Only the first unit is taken through manufacturing.
    for step in (ManufacturingStep.PRINTED, ManufacturingStep.QC_PASSED,
                 ManufacturingStep.COATED):
        record_completion(unit=units[0], step=step, completed_at=timezone.now(),
                          recorded_by=actor["user"], source_reference="log")

    client = APIClient()
    sign_in(client, actor)
    response = client.post(
        reverse("staff-activation-jobs"),
        {"batch": str(actor["batch"].id)},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["succeeded"] == 1
    assert response.data["failed"] == 1
    assert response.data["status"] == "COMPLETED_WITH_FAILURES"
    assert response.data["failures"], "the portal must be able to show why"


# --- CSRF -------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_state_changing_staff_requests_require_csrf(make_manufacturer):
    """Cookie-authenticated writes must carry a CSRF token.

    DRF's test client skips CSRF by default, so this one opts in. Without it the
    suite would pass while the real portal got 403s -- which is exactly what
    happened when the endpoints were first exercised over HTTP.
    """
    actor = make_manufacturer("Alpha")

    # A CSRF-enforcing client, mirroring a real browser.
    strict = APIClient(enforce_csrf_checks=True)
    strict.post(
        reverse("staff-login"),
        {"username": actor["user"].get_username(), "password": PASSWORD},
        format="json",
    )
    response = strict.post(
        reverse("staff-mfa-verify"),
        {"code": mfa.now_code(actor["membership"].totp_secret)},
        format="json",
    )
    assert response.status_code == 403
    assert "CSRF" in str(response.data.get("detail", ""))


@pytest.mark.django_db(transaction=True)
def test_reads_are_not_blocked_by_csrf(make_manufacturer):
    """Safe methods stay reachable, so a portal can bootstrap its token."""
    actor = make_manufacturer("Alpha")
    strict = APIClient(enforce_csrf_checks=True)
    strict.post(
        reverse("staff-login"),
        {"username": actor["user"].get_username(), "password": PASSWORD},
        format="json",
    )
    # GET is exempt; the role still requires MFA, so 403 comes from the factor,
    # not from CSRF.
    response = strict.get(reverse("staff-me"))
    assert response.status_code in (200, 403)
    assert "CSRF" not in str(response.data.get("detail", ""))


@pytest.mark.django_db(transaction=True)
def test_portal_origin_is_trusted_for_csrf(settings):
    """The portal's origin must be named, or every staff write fails CSRF.

    Django checks the Origin header on cookie-authenticated writes. Behind nginx
    the portal and API share an origin and this passes on its own, but a
    separately-served portal needs naming -- and the failure reads like a
    permissions problem, not a configuration one.
    """
    assert settings.CSRF_TRUSTED_ORIGINS, "no trusted origins configured"
    assert any("3000" in o or "3100" in o for o in settings.CSRF_TRUSTED_ORIGINS), (
        "the development portal origin is not trusted"
    )


# --- MFA recovery -----------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_admin_can_reset_a_lost_second_factor(platform_admin, make_manufacturer):
    """Losing a phone must not lock someone out of a privileged role forever."""
    target = make_manufacturer("Alpha")
    assert target["membership"].mfa_satisfied

    client = APIClient()
    sign_in(client, platform_admin)
    response = client.post(
        reverse("admin-membership-reset-mfa", args=[target["membership"].id]),
        {},
        format="json",
    )
    assert response.status_code == 200

    target["membership"].refresh_from_db()
    assert not target["membership"].mfa_satisfied
    assert target["membership"].totp_secret == ""


@pytest.mark.django_db(transaction=True)
def test_resetting_the_factor_does_not_grant_access(platform_admin, make_manufacturer):
    """After a reset the next sign-in must land in enrolment, not straight in."""
    target = make_manufacturer("Alpha")
    admin_client = APIClient()
    sign_in(admin_client, platform_admin)
    admin_client.post(
        reverse("admin-membership-reset-mfa", args=[target["membership"].id]),
        {}, format="json",
    )

    client = APIClient()
    login = client.post(
        reverse("staff-login"),
        {"username": target["user"].get_username(), "password": PASSWORD},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["mfa_required"] is True
    assert login.data["mfa_enrolled"] is False
    # And the password-only session still reaches nothing.
    assert client.get(reverse("staff-products")).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_a_reset_is_recorded_in_the_audit_trail(platform_admin, make_manufacturer):
    from apps.audit.models import AuditAction, AuditEvent

    target = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, platform_admin)
    client.post(
        reverse("admin-membership-reset-mfa", args=[target["membership"].id]),
        {}, format="json",
    )

    event = AuditEvent.objects.filter(action=AuditAction.STAFF_MFA_RESET).first()
    assert event is not None
    assert target["user"].get_username() in event.reason
    # The secret must never appear in an audit record.
    assert "totp" not in str(event.detail).lower()


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_reset_anyone(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")
    client = APIClient()
    sign_in(client, alpha)

    for target in (alpha, beta):
        response = client.post(
            reverse("admin-membership-reset-mfa", args=[target["membership"].id]),
            {}, format="json",
        )
        assert response.status_code == 403


# --- unit blocking and retry ------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_blocking_a_unit_stops_later_first_verifications(make_manufacturer):
    from apps.verification.models import VerificationOutcome
    from apps.verification.services import confirm_verification
    from tests.conftest import make_session_and_challenge

    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=1)
    unit = PackageUnit.objects.get(pk=result.units[0].unit_id)
    for step in (ManufacturingStep.PRINTED, ManufacturingStep.QC_PASSED,
                 ManufacturingStep.COATED):
        record_completion(unit=unit, step=step, completed_at=timezone.now(),
                          recorded_by=actor["user"], source_reference="log")

    client = APIClient()
    sign_in(client, actor)
    client.post(reverse("staff-activation-jobs"),
                {"batch": str(actor["batch"].id)}, format="json")

    blocked = client.post(
        reverse("staff-unit-block", args=[unit.id]),
        {"reason": "Reported as tampered"},
        format="json",
    )
    assert blocked.status_code == 200

    unit.refresh_from_db()
    assert unit.is_blocked

    session, challenge = make_session_and_challenge(unit)
    outcome = confirm_verification(
        session=session, unit_id=unit.id, challenge_id=challenge.id,
        idempotency_key="after-block", body={"u": str(unit.id)},
    )
    assert outcome.outcome == VerificationOutcome.RESTRICTED
    assert not outcome.first_redemption


@pytest.mark.django_db(transaction=True)
def test_manufacturer_cannot_block_another_manufacturers_unit(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")
    unit = PackageUnit.objects.get(
        pk=create_print_job(batch=beta["batch"], count=1).units[0].unit_id
    )

    client = APIClient()
    sign_in(client, alpha)
    response = client.post(
        reverse("staff-unit-block", args=[unit.id]), {"reason": "x"}, format="json"
    )
    assert response.status_code == 404
    unit.refresh_from_db()
    assert not unit.is_blocked


@pytest.mark.django_db(transaction=True)
def test_admin_can_block_a_unit_in_an_emergency(platform_admin, make_manufacturer):
    """Emergency restriction is an admin function, unlike activation."""
    target = make_manufacturer("Alpha")
    unit = PackageUnit.objects.get(
        pk=create_print_job(batch=target["batch"], count=1).units[0].unit_id
    )

    client = APIClient()
    sign_in(client, platform_admin)
    response = client.post(
        reverse("staff-unit-block", args=[unit.id]),
        {"reason": "Regulator instruction"},
        format="json",
    )
    assert response.status_code == 200
    unit.refresh_from_db()
    assert unit.is_blocked
