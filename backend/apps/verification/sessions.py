"""Anonymous consumer sessions.

A session identifies an installation, not a person. No phone number and no
account is involved. The credential is a random opaque string returned exactly
once; the database stores only its digest, so a database reader cannot
impersonate an installation.

Reinstalling the app produces a new session. That is a new installation
identity, and it is not evidence that a different person is scanning.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.verification.models import ConsumerSession

SESSION_TTL_DAYS = 365
CREDENTIAL_BYTES = 32


@dataclass(frozen=True)
class IssuedSession:
    """A new session and its credential.

    The credential is returned once and never recoverable afterwards.
    """

    session: ConsumerSession
    credential: str


def hash_credential(credential: str) -> bytes:
    return hashlib.sha256(credential.encode("ascii")).digest()


def create_session(*, app_id: str = "", installation_id: str = "") -> IssuedSession:
    """Create a session. Callers must verify attestation first."""
    credential = secrets.token_urlsafe(CREDENTIAL_BYTES)
    session = ConsumerSession.objects.create(
        credential_sha256=hash_credential(credential),
        app_id=app_id,
        installation_id=installation_id,
        expires_at=timezone.now() + timedelta(days=SESSION_TTL_DAYS),
    )
    return IssuedSession(session=session, credential=credential)


def resolve_session(credential: str) -> ConsumerSession | None:
    """Return the usable session for ``credential``, or None."""
    if not credential:
        return None
    session = ConsumerSession.objects.filter(
        credential_sha256=hash_credential(credential)
    ).first()
    if session is None or not session.is_usable(timezone.now()):
        return None
    return session


def touch(session: ConsumerSession) -> None:
    session.last_seen_at = timezone.now()
    session.save(update_fields=["last_seen_at"])


def revoke(session: ConsumerSession) -> None:
    session.revoked_at = timezone.now()
    session.save(update_fields=["revoked_at"])
