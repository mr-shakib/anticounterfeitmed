"""Optional prescribing information: entered in the portal, signed to the app.

The text is what a patient reads about dosage and side effects, so two things
matter beyond storing it: it reaches the app only inside a signed statement,
and only alongside a package the app may show.
"""

from __future__ import annotations

import base64

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditAction, AuditEvent
from apps.catalog.models import PRODUCT_INFORMATION_MAX_CHARS, Product
from medcrypto.canonical import parse_strict
from medcrypto.contexts import Context
from medcrypto.signing import verify_ok
from tests.test_api import (  # noqa: F401
    _allow_insecure_attestation,
    active_package,
    auth,
    make_session,
    platform_keys,
)
from tests.test_end_to_end import factory, take_through_manufacturing  # noqa: F401
from tests.test_staff_api import make_manufacturer, sign_in  # noqa: F401

INFORMATION = {
    "indications": "Peptic ulcer diseases\nGastroesophageal reflux diseases",
    "dosage_administration": "40 mg daily in the morning for 4 weeks.",
    "storage_conditions": "Keep in a dry place, away from light and heat.",
}


def _product(client, **extra):
    return client.post(
        reverse("staff-products"),
        {
            "brand": "Pantonix", "generic": "Pantoprazole", "strength": "20 mg",
            "dosage_form": "Tablet", "pack_description": "Strip of 10",
            **extra,
        },
        format="json",
    )


# --- the portal side ----------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_a_product_can_carry_optional_information(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)

    without = _product(client)
    with_info = _product(client, information={**INFORMATION, "pharmacology": "   "})

    assert without.status_code == 201
    assert without.data["information"] == {}
    assert with_info.status_code == 201, with_info.data
    # Trimmed, and an empty section is dropped rather than stored blank.
    assert with_info.data["information"] == INFORMATION


@pytest.mark.django_db(transaction=True)
def test_unknown_or_oversized_sections_are_refused(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)

    unknown = _product(client, information={"cure_rate": "100%"})
    too_long = _product(
        client, information={"indications": "x" * (PRODUCT_INFORMATION_MAX_CHARS + 1)}
    )
    too_much = _product(
        client,
        # Bangla is three bytes a character; the total is counted in bytes.
        information={f: "অ" * 3000 for f in (
            "indications", "pharmacology", "dosage_administration",
            "interaction", "contraindications", "side_effects",
        )},
    )

    assert unknown.status_code == 400
    assert too_long.status_code == 400
    assert too_much.status_code == 400
    assert not Product.objects.filter(brand="Pantonix").exists()


@pytest.mark.django_db(transaction=True)
def test_information_can_be_edited_and_the_edit_is_recorded(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)
    product = actor["product"]

    response = client.patch(
        reverse("staff-product-information", args=[product.id]),
        {"information": INFORMATION, "brand": "Renamed"},
        format="json",
    )

    assert response.status_code == 200, response.data
    product.refresh_from_db()
    assert product.information == INFORMATION
    assert product.brand != "Renamed", "only the information is editable"
    event = AuditEvent.objects.get(action=AuditAction.PRODUCT_INFORMATION_UPDATED)
    assert event.detail["sections_after"] == sorted(INFORMATION)


@pytest.mark.django_db(transaction=True)
def test_another_manufacturer_cannot_edit_it(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")
    client = APIClient()
    sign_in(client, alpha)

    response = client.patch(
        reverse("staff-product-information", args=[beta["product"].id]),
        {"information": {"indications": "forged"}},
        format="json",
    )

    assert response.status_code == 404
    beta["product"].refresh_from_db()
    assert beta["product"].information == {}


# --- the app side ---------------------------------------------------------------


def _prepare(client, token):
    credential = make_session(client)
    response = client.post(
        reverse("consumer-prepare"),
        {"token": token, "nonce": "n-123"},
        format="json",
        **auth(credential),
    )
    assert response.status_code == 200, response.data
    return response.data


def _signed_record(envelope, public_key: bytes) -> dict:
    payload = base64.b64decode(envelope["payload"])
    assert verify_ok(
        public_key, Context.STATUS, payload, base64.b64decode(envelope["signature"])
    ), "the information must arrive under a valid signature"
    return parse_strict(payload)


@pytest.mark.django_db(transaction=True)
def test_the_app_receives_the_information_signed_and_in_order(client, active_package):
    from apps.trust.models import KeyPurpose, SigningKey

    _org, unit, token = active_package
    product = unit.batch.product
    product.information = INFORMATION
    product.save(update_fields=["information"])

    data = _prepare(client, token)
    key = SigningKey.objects.get(purpose=KeyPurpose.STATUS)
    record = _signed_record(data["status"], bytes(key.public_key))

    assert [e["field"] for e in record["product_information"]] == [
        "indications", "dosage_administration", "storage_conditions",
    ]
    assert record["product_information"][0]["text"] == INFORMATION["indications"]


@pytest.mark.django_db(transaction=True)
def test_without_information_the_statement_is_unchanged(client, active_package):
    from apps.trust.models import KeyPurpose, SigningKey

    _org, _unit, token = active_package
    data = _prepare(client, token)
    key = SigningKey.objects.get(purpose=KeyPurpose.STATUS)

    assert "product_information" not in _signed_record(data["status"], bytes(key.public_key))


@pytest.mark.django_db(transaction=True)
def test_a_recalled_package_gets_no_information(client, active_package):
    from apps.trust.models import KeyPurpose, SigningKey

    _org, unit, token = active_package
    product = unit.batch.product
    product.information = INFORMATION
    product.save(update_fields=["information"])
    batch = unit.batch
    batch.is_recalled = True
    batch.save(update_fields=["is_recalled"])

    data = _prepare(client, token)
    key = SigningKey.objects.get(purpose=KeyPurpose.STATUS)

    assert data["activation_credential"] is None
    assert "product_information" not in _signed_record(data["status"], bytes(key.public_key))
