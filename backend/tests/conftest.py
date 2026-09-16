"""Shared fixtures.

Tests run against real PostgreSQL. SQLite cannot exercise row locks or partial
unique indexes, so it would report a pass on exactly the guarantees that matter
most here.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Batch, Product
from apps.organizations.models import ApprovalStatus, Organization, OrganizationType
from apps.serialization.models import PackageUnit, UnitLifecycle
from apps.verification.models import ConsumerSession, VerificationChallenge
from medcrypto import generate_token, hash_token


@pytest.fixture
def manufacturer(db):
    return Organization.objects.create(
        type=OrganizationType.MANUFACTURER,
        name="Test Pharmaceuticals Ltd",
        approval_status=ApprovalStatus.APPROVED,
        approved_at=timezone.now(),
    )


@pytest.fixture
def batch(manufacturer):
    product = Product.objects.create(
        manufacturer=manufacturer,
        brand="Napa",
        generic="Paracetamol",
        strength="500 mg",
        dosage_form="Tablet",
        pack_description="Strip of 10 tablets",
    )
    return Batch.objects.create(
        product=product,
        batch_number="BN-2026-0042",
        manufactured_on=date.today() - timedelta(days=30),
        expires_on=date.today() + timedelta(days=365),
        planned_unit_count=1000,
    )


def make_active_unit(batch, reference="UNIT-0001") -> tuple[PackageUnit, str]:
    """Create one ACTIVE unit and return it with its raw token.

    The raw token is returned to the caller and never stored; only its digest
    reaches the database.
    """
    token = generate_token()
    unit = PackageUnit.objects.create(
        batch=batch,
        external_reference=reference,
        token_sha256=hash_token(token),
        lifecycle=UnitLifecycle.ACTIVE,
        activated_at=timezone.now(),
    )
    return unit, token


@pytest.fixture
def active_unit(batch):
    unit, _token = make_active_unit(batch)
    return unit


def make_session_and_challenge(unit, ttl_seconds: int = 120):
    import hashlib
    import secrets

    credential = secrets.token_bytes(32)
    session = ConsumerSession.objects.create(
        credential_sha256=hashlib.sha256(credential).digest(),
        expires_at=timezone.now() + timedelta(days=30),
    )
    challenge = VerificationChallenge.objects.create(
        session=session,
        unit=unit,
        credential_version=unit.version,
        expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
    )
    return session, challenge
