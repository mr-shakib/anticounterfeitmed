"""TOTP second factor for staff.

Privileged staff must hold a second factor: a release manager can put units into
circulation and a platform admin can suspend an issuer, so a stolen password
alone must not be enough.

The shared secret is stored per membership. Treat it as credential material: it
never appears in logs, audit records or API responses once enrolment is
confirmed.
"""

from __future__ import annotations

import pyotp
from django.utils import timezone

#: Accept one step either side of now, to tolerate clock drift on cheap phones.
VALID_WINDOW = 1

ISSUER = "MedSecure PQC"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str) -> str:
    """The otpauth:// URI an authenticator app scans during enrolment."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=ISSUER)


def verify_code(secret: str, code: str) -> bool:
    """Check a submitted code against the secret.

    Returns False rather than raising for anything malformed, so a bad input can
    never be mistaken for a pass.
    """
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=VALID_WINDOW)
    except Exception:
        return False


def now_code(secret: str) -> str:
    """Current code. For tests and local development only."""
    return pyotp.TOTP(secret).now()
