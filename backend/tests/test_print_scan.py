"""The print-line scan: the one manufacturing record this system observes.

Two things are being protected here. The first is the honesty of the record --
a scan is stored as evidence and a typed entry as an assertion, and nothing may
blur them. The second is the raw token, which this is the only staff endpoint
ever to see: it must not reach the response, the stored event, or the audit
trail.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.organizations.models import StaffRole
from apps.qc.models import ManufacturingCompletionEvent, ManufacturingStep
from apps.qc.services import batch_manufacturing_progress
from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.serialization.services import create_print_job
from tests.test_staff_api import make_manufacturer, sign_in  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def scan(client, batch_id, token):
    return client.post(
        reverse("staff-print-scans"),
        {"batch": str(batch_id), "token": token},
        format="json",
    )


@pytest.fixture
def line(make_manufacturer):  # noqa: F811
    """A manufacturer with a printed run, and the raw tokens for it."""
    actor = make_manufacturer("Alpha", role=StaffRole.MANUFACTURER_STAFF)
    issued = create_print_job(batch=actor["batch"], count=3).units
    client = APIClient()
    sign_in(client, actor)
    return {"actor": actor, "issued": issued, "client": client}


def test_a_scan_records_the_print_as_evidence(line):
    issued = line["issued"][0]

    response = scan(line["client"], line["actor"]["batch"].id, issued.token)

    assert response.status_code == 200, response.data
    assert response.data["outcome"] == "RECORDED"
    assert response.data["external_reference"] == issued.external_reference
    assert response.data["units_scan_verified"] == 1
    assert response.data["units_total"] == 3

    event = ManufacturingCompletionEvent.objects.get(unit_id=issued.unit_id)
    assert event.step == ManufacturingStep.PRINTED
    # The distinction the whole feature rests on.
    assert event.is_manufacturer_asserted is False
    assert PackageUnit.objects.get(pk=issued.unit_id).lifecycle == UnitLifecycle.PRINTED


def test_the_raw_token_is_never_written_down(line):
    issued = line["issued"][0]

    response = scan(line["client"], line["actor"]["batch"].id, issued.token)

    assert issued.token not in str(response.data)
    event = ManufacturingCompletionEvent.objects.get(unit_id=issued.unit_id)
    assert issued.token not in event.source_reference
    assert issued.token not in event.reason
    for audit in AuditEvent.objects.filter(unit_id=issued.unit_id):
        assert issued.token not in str(audit.detail)
        assert issued.token not in audit.reason


def test_a_hand_entered_print_is_reported_as_such(line):
    """So nobody reads "already scanned" over a record nobody scanned."""
    batch = line["actor"]["batch"]
    issued = line["issued"][0]
    line["client"].post(
        reverse("staff-manufacturing-confirmations"),
        {
            "batch": str(batch.id),
            "step": ManufacturingStep.PRINTED,
            "completed_at": timezone.now().isoformat(),
            "source_reference": "production log",
        },
        format="json",
    )

    response = scan(line["client"], batch.id, issued.token)

    assert response.data["outcome"] == "ALREADY_RECORDED"
    assert response.data["units_scan_verified"] == 0


def test_rescanning_the_same_label_is_not_an_error(line):
    """A line re-reads labels. Refusing would push someone around the system."""
    issued = line["issued"][0]

    first = scan(line["client"], line["actor"]["batch"].id, issued.token)
    again = scan(line["client"], line["actor"]["batch"].id, issued.token)

    assert first.data["outcome"] == "RECORDED"
    assert again.data["outcome"] == "ALREADY_SCANNED"
    assert again.data["units_scan_verified"] == 1
    assert ManufacturingCompletionEvent.objects.filter(unit_id=issued.unit_id).count() == 1


def test_a_code_from_another_batch_matches_nothing(line, make_manufacturer):  # noqa: F811
    """And is told so in the same words as a code that does not exist at all."""
    other = make_manufacturer("Beta")
    stranger = create_print_job(batch=other["batch"], count=1).units[0]

    response = scan(line["client"], line["actor"]["batch"].id, stranger.token)

    assert response.status_code == 200
    assert response.data["outcome"] == "NOT_MATCHED"
    assert response.data["units_scan_verified"] == 0
    assert not ManufacturingCompletionEvent.objects.filter(
        unit_id=stranger.unit_id
    ).exists()
    assert PackageUnit.objects.get(pk=stranger.unit_id).lifecycle == UnitLifecycle.CREATED


def test_a_malformed_code_says_nothing_extra(line):
    response = scan(line["client"], line["actor"]["batch"].id, "not-a-token")

    assert response.status_code == 200
    assert response.data["outcome"] == "NOT_MATCHED"


def test_another_manufacturer_cannot_scan_into_this_batch(line, make_manufacturer):  # noqa: F811
    beta = make_manufacturer("Beta")
    intruder = APIClient()
    sign_in(intruder, beta)

    response = scan(intruder, line["actor"]["batch"].id, line["issued"][0].token)

    assert response.status_code == 404
    assert ManufacturingCompletionEvent.objects.count() == 0


def test_a_unit_past_the_print_line_is_refused(line):
    """Scanning is a print-line record.

    Accepting one later would turn the endpoint into a way of confirming the
    tokens of medicine already on its way to a patient.
    """
    issued = line["issued"][0]
    unit = PackageUnit.objects.get(pk=issued.unit_id)
    unit.lifecycle = UnitLifecycle.COVERED
    unit.save(update_fields=["lifecycle"])

    response = scan(line["client"], line["actor"]["batch"].id, issued.token)

    assert response.data["outcome"] == "NOT_APPLICABLE"
    assert not ManufacturingCompletionEvent.objects.filter(unit=unit).exists()


def test_a_blocked_unit_is_refused(line):
    issued = line["issued"][0]
    unit = PackageUnit.objects.get(pk=issued.unit_id)
    unit.is_blocked = True
    unit.save(update_fields=["is_blocked"])

    response = scan(line["client"], line["actor"]["batch"].id, issued.token)

    assert response.data["outcome"] == "NOT_APPLICABLE"


def test_the_release_manager_sees_the_running_count(line):
    """The scan count is what step 2 of the batch page reports, unaided."""
    batch = line["actor"]["batch"]
    for issued in line["issued"][:2]:
        scan(line["client"], batch.id, issued.token)

    progress = batch_manufacturing_progress(batch.id)

    assert progress["counts_by_step"][ManufacturingStep.PRINTED] == 2
    assert progress["units_scan_verified"] == 2
    # Printing alone is not enough to activate: QC and coating are still owed,
    # and no scan can evidence a coating that is applied after scanning.
    assert progress["units_ready"] == 0


def test_a_typed_record_is_not_counted_as_scan_evidence(line):
    batch = line["actor"]["batch"]

    line["client"].post(
        reverse("staff-manufacturing-confirmations"),
        {
            "batch": str(batch.id),
            "step": ManufacturingStep.PRINTED,
            "completed_at": timezone.now().isoformat(),
            "source_reference": "production log",
        },
        format="json",
    )

    progress = batch_manufacturing_progress(batch.id)
    assert progress["counts_by_step"][ManufacturingStep.PRINTED] == 3
    assert progress["units_scan_verified"] == 0
