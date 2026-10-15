"""The label sheet layout: one per organization, set in the portal's settings.

The layout decides what the printable sheet and PDF carry besides the codes.
Its defaults carry nothing else, so a sheet nobody has configured goes to the
printer as codes alone, 15 mm apart.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditAction, AuditEvent
from apps.organizations.models import StaffRole
from apps.serialization.models import LabelLayout
from tests.test_staff_api import make_manufacturer, platform_admin, sign_in  # noqa: F401

#: Pinned here and in staff-web/lib/labelPrint.test.ts, so the portal's
#: fallback cannot drift from what the server hands out.
DEFAULTS = {
    "page_size": "A4",
    "page_margin_mm": 10.0,
    "gap_mm": 15.0,
    "footprint_mm": 20,
    "show_header": False,
    "header_text": "",
    "show_reference": False,
}

CUSTOM = {
    "page_size": "LETTER",
    "page_margin_mm": 7.5,
    "gap_mm": 20,
    "footprint_mm": 25,
    "show_header": True,
    "header_text": "Batch {batch} — {count} labels",
    "show_reference": True,
}


def _client(actor) -> APIClient:
    client = APIClient()
    sign_in(client, actor)
    return client


def _settings(response) -> dict:
    data = dict(response.data)
    data.pop("updated_at")
    return {k: float(v) if k.endswith("_mm") and k != "footprint_mm" else v
            for k, v in data.items()}


def test_an_unconfigured_organization_prints_codes_alone(make_manufacturer):
    client = _client(make_manufacturer("Alpha"))

    response = client.get(reverse("staff-label-layout"))

    assert response.status_code == 200
    assert _settings(response) == DEFAULTS
    assert not LabelLayout.objects.exists(), "reading the defaults stores nothing"


def test_saving_the_layout_is_recorded(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = _client(actor)

    saved = client.patch(reverse("staff-label-layout"), CUSTOM, format="json")

    assert saved.status_code == 200, saved.data
    assert _settings(client.get(reverse("staff-label-layout"))) == {
        **CUSTOM, "page_margin_mm": 7.5, "gap_mm": 20.0,
    }
    event = AuditEvent.objects.get(action=AuditAction.LABEL_LAYOUT_UPDATED)
    assert event.organization == actor["org"]
    assert event.actor_user == actor["user"]
    assert event.detail["before"] == DEFAULTS
    assert event.detail["after"]["gap_mm"] == 20.0
    assert event.detail["after"]["header_text"] == CUSTOM["header_text"]


def test_ordinary_staff_can_set_it_too(make_manufacturer):
    client = _client(make_manufacturer("Alpha", role=StaffRole.MANUFACTURER_STAFF))

    response = client.patch(reverse("staff-label-layout"), {"gap_mm": 18}, format="json")

    assert response.status_code == 200, response.data
    assert response.data["gap_mm"] == 18
    assert response.data["show_header"] is False


def test_each_organization_has_its_own(make_manufacturer):
    alpha = _client(make_manufacturer("Alpha"))
    beta = _client(make_manufacturer("Beta"))

    alpha.patch(reverse("staff-label-layout"), CUSTOM, format="json")

    assert _settings(beta.get(reverse("staff-label-layout"))) == DEFAULTS


@pytest.mark.parametrize(
    "change",
    [
        {"gap_mm": -1},
        {"gap_mm": 100.5},
        {"page_margin_mm": 51},
        {"footprint_mm": 7},
        {"page_size": "A3"},
        {"header_text": "x" * 121},
        {"header_text": "Batch {batch}\nsecond line"},
    ],
)
def test_out_of_range_values_are_refused(make_manufacturer, change):
    client = _client(make_manufacturer("Alpha"))

    response = client.patch(reverse("staff-label-layout"), change, format="json")

    assert response.status_code == 400
    assert not LabelLayout.objects.exists()
    assert not AuditEvent.objects.filter(action=AuditAction.LABEL_LAYOUT_UPDATED).exists()


def test_platform_admin_and_anonymous_are_refused(platform_admin):
    assert _client(platform_admin).get(reverse("staff-label-layout")).status_code == 403
    assert APIClient().get(reverse("staff-label-layout")).status_code == 403
