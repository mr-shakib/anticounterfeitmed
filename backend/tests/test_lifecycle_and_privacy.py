"""Lifecycle constraints and the token-storage invariant."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.serialization.models import ALLOWED_TRANSITIONS, PackageUnit, UnitLifecycle
from apps.verification.models import (
    VerificationEvent,
    VerificationEventType,
)
from apps.verification.services import ChallengeInvalid, confirm_verification
from medcrypto import generate_token, hash_token
from tests.conftest import make_active_unit, make_session_and_challenge


def test_redeemed_and_void_are_terminal():
    assert ALLOWED_TRANSITIONS[UnitLifecycle.REDEEMED] == frozenset()
    assert ALLOWED_TRANSITIONS[UnitLifecycle.VOID] == frozenset()
    # Nothing may transition back into ACTIVE from REDEEMED.
    for source, targets in ALLOWED_TRANSITIONS.items():
        if source == UnitLifecycle.REDEEMED:
            assert UnitLifecycle.ACTIVE not in targets


def test_manufacturing_prerequisites_are_ordered():
    assert UnitLifecycle.ACTIVE in ALLOWED_TRANSITIONS[UnitLifecycle.COVERED]
    # A unit cannot jump from CREATED or PRINTED straight to ACTIVE.
    assert UnitLifecycle.ACTIVE not in ALLOWED_TRANSITIONS[UnitLifecycle.CREATED]
    assert UnitLifecycle.ACTIVE not in ALLOWED_TRANSITIONS[UnitLifecycle.PRINTED]
    assert UnitLifecycle.ACTIVE not in ALLOWED_TRANSITIONS[UnitLifecycle.QC_PASSED]


@pytest.mark.django_db
def test_raw_token_is_never_stored(batch):
    """Scan every text column in the database for the raw token."""
    unit, token = make_active_unit(batch, reference="UNIT-PRIVACY")

    assert bytes(unit.token_sha256) == hash_token(token)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND data_type IN ('text','character varying','jsonb','json')
            """
        )
        columns = cursor.fetchall()

        hits = []
        for table, column in columns:
            cursor.execute(
                f'SELECT count(*) FROM "{table}" WHERE CAST("{column}" AS text) LIKE %s',
                [f"%{token}%"],
            )
            if cursor.fetchone()[0]:
                hits.append(f"{table}.{column}")

    assert not hits, f"raw token found in: {hits}"


@pytest.mark.django_db
def test_token_lookup_is_by_digest(batch):
    unit, token = make_active_unit(batch, reference="UNIT-LOOKUP")
    found = PackageUnit.objects.get(token_sha256=hash_token(token))
    assert found.id == unit.id
    # An unrelated token resolves to nothing.
    assert not PackageUnit.objects.filter(token_sha256=hash_token(generate_token())).exists()


@pytest.mark.django_db(transaction=True)
def test_expired_challenge_cannot_be_spent(batch):
    unit, _token = make_active_unit(batch, reference="UNIT-EXPIRED-CHAL")
    session, challenge = make_session_and_challenge(unit)
    challenge.expires_at = timezone.now() - timedelta(seconds=1)
    challenge.save(update_fields=["expires_at"])

    with pytest.raises(ChallengeInvalid):
        confirm_verification(
            session=session,
            unit_id=unit.id,
            challenge_id=challenge.id,
            idempotency_key="expired-key",
            body={"unit": str(unit.id)},
        )
    assert not VerificationEvent.objects.filter(unit=unit).exists()


@pytest.mark.django_db(transaction=True)
def test_challenge_bound_to_previewed_version(batch):
    """A unit that changed after the preview invalidates the challenge."""
    unit, _token = make_active_unit(batch, reference="UNIT-VERSION")
    session, challenge = make_session_and_challenge(unit)

    unit.version += 1
    unit.save(update_fields=["version"])

    with pytest.raises(ChallengeInvalid):
        confirm_verification(
            session=session,
            unit_id=unit.id,
            challenge_id=challenge.id,
            idempotency_key="version-key",
            body={"unit": str(unit.id)},
        )


@pytest.mark.django_db(transaction=True)
def test_challenge_cannot_be_reused_across_sessions(batch):
    """A challenge issued to one session must not work for another."""
    unit, _token = make_active_unit(batch, reference="UNIT-CROSS")
    session_a, challenge_a = make_session_and_challenge(unit)
    session_b, _challenge_b = make_session_and_challenge(unit)

    with pytest.raises(ChallengeInvalid):
        confirm_verification(
            session=session_b,
            unit_id=unit.id,
            challenge_id=challenge_a.id,
            idempotency_key="cross-key",
            body={"unit": str(unit.id)},
        )


@pytest.mark.django_db(transaction=True)
def test_inactive_unit_records_preactivation_attempt(batch):
    """Scanning a covered-but-not-activated unit must not redeem it."""
    unit, _token = make_active_unit(batch, reference="UNIT-INACTIVE")
    unit.lifecycle = UnitLifecycle.COVERED
    unit.save(update_fields=["lifecycle"])
    session, challenge = make_session_and_challenge(unit)

    result = confirm_verification(
        session=session,
        unit_id=unit.id,
        challenge_id=challenge.id,
        idempotency_key="inactive-key",
        body={"unit": str(unit.id)},
    )

    assert result.outcome == "NOT_ACTIVATED"
    assert not result.first_redemption
    unit.refresh_from_db()
    assert unit.lifecycle == UnitLifecycle.COVERED
    assert VerificationEvent.objects.filter(
        unit=unit, event_type=VerificationEventType.PREACTIVATION_ATTEMPT
    ).exists()
