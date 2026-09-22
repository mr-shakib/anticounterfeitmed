"""Retained label exports.

The SRS keeps encrypted print artifacts until a job is reconciled and deletes
them within 24 hours. These tests hold that line from both sides: the labels are
retrievable while they should be, and genuinely unrecoverable once they are not.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.serialization.export_store import decrypt_export
from apps.serialization.models import PrintJob
from apps.serialization.services import (
    create_print_job,
    purge_expired_exports,
    reconcile_print_job,
)
from tests.test_staff_api import (  # noqa: F401
    PASSWORD,
    make_manufacturer,
    platform_admin,
    sign_in,
)


@pytest.mark.django_db(transaction=True)
def test_export_is_retrievable_after_leaving_the_page(make_manufacturer):
    """The reason this exists: navigating away must not lose a run of labels."""
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)

    created = client.post(
        reverse("staff-print-jobs"),
        {"batch": str(actor["batch"].id), "count": 4},
        format="json",
    )
    assert created.status_code == 201
    issued = {e["qr"]["data_codewords"] for e in created.data["label_export"]}
    job_id = created.data["print_job"]["id"]

    # A completely separate request, as if the page had been closed and reopened.
    again = client.get(reverse("staff-print-job-export", args=[job_id]))
    assert again.status_code == 200
    assert {e["qr"]["data_codewords"] for e in again.data["label_export"]} == issued


@pytest.mark.django_db(transaction=True)
def test_the_export_is_encrypted_at_rest(make_manufacturer):
    """A database copy must not hand over the tokens."""
    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=3)
    token = result.units[0].token

    job = PrintJob.objects.get(pk=result.print_job.id)
    raw = bytes(job.export_ciphertext)
    assert token.encode() not in raw, "the token is readable in the stored blob"

    # The application can still recover it.
    assert any(e["token"] == token for e in decrypt_export(raw))


@pytest.mark.django_db(transaction=True)
def test_reconciling_shortens_the_retention(make_manufacturer, settings):
    settings.EXPORT_GRACE_HOURS_AFTER_RECONCILE = 24

    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=2)
    job = result.print_job
    original = job.export_expires_at

    reconcile_print_job(job=job, printed=2, rejected=0)
    job.refresh_from_db()

    assert job.export_expires_at < original
    assert job.export_expires_at <= timezone.now() + timedelta(hours=24, minutes=1)


@pytest.mark.django_db(transaction=True)
def test_an_expired_export_is_gone_and_says_so(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)

    created = client.post(
        reverse("staff-print-jobs"),
        {"batch": str(actor["batch"].id), "count": 2},
        format="json",
    )
    job_id = created.data["print_job"]["id"]

    job = PrintJob.objects.get(pk=job_id)
    job.export_expires_at = timezone.now() - timedelta(minutes=1)
    job.save(update_fields=["export_expires_at"])

    response = client.get(reverse("staff-print-job-export", args=[job_id]))
    assert response.status_code == 410
    assert response.data["code"] == "EXPORT_UNAVAILABLE"
    # The message has to tell someone what to do instead.
    assert "void" in response.data["detail"].lower()


@pytest.mark.django_db(transaction=True)
def test_purging_removes_the_ciphertext_and_records_it(make_manufacturer):
    """Disposal of an artifact holding raw tokens must be visible, not silent."""
    actor = make_manufacturer("Alpha")
    result = create_print_job(batch=actor["batch"], count=2)
    job = result.print_job
    job.export_expires_at = timezone.now() - timedelta(minutes=1)
    job.save(update_fields=["export_expires_at"])

    assert purge_expired_exports() == 1

    job.refresh_from_db()
    assert not job.export_ciphertext
    assert job.export_deleted_at is not None

    # Running again is harmless and finds nothing.
    assert purge_expired_exports() == 0


@pytest.mark.django_db(transaction=True)
def test_another_manufacturer_cannot_fetch_an_export(make_manufacturer):
    alpha = make_manufacturer("Alpha")
    beta = make_manufacturer("Beta")
    theirs = create_print_job(batch=beta["batch"], count=2)

    client = APIClient()
    sign_in(client, alpha)
    response = client.get(
        reverse("staff-print-job-export", args=[theirs.print_job.id])
    )
    assert response.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_batch_lists_its_print_jobs_with_availability(make_manufacturer):
    actor = make_manufacturer("Alpha")
    client = APIClient()
    sign_in(client, actor)
    client.post(
        reverse("staff-print-jobs"),
        {"batch": str(actor["batch"].id), "count": 2},
        format="json",
    )

    listed = client.get(reverse("staff-batch-print-jobs", args=[actor["batch"].id]))
    assert listed.status_code == 200
    assert len(listed.data) == 1
    assert listed.data[0]["export_available"] is True
    assert listed.data[0]["issued_count"] == 2
