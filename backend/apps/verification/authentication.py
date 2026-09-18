"""DRF authentication and permissions for consumer endpoints.

Both credentials are mandatory on every consumer endpoint:

* a session credential, in ``Authorization: Session <credential>``;
* an app attestation token, in ``X-App-Check``.

A staff session is never accepted here, and a header such as ``X-Our-App``, an
embedded API key, a CORS rule or a user-agent string is not authorization.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from rest_framework import authentication, exceptions, permissions

from apps.verification import sessions
from apps.verification.attestation import AttestationFailed, get_attestation_verifier


class AttestationUnavailable(exceptions.APIException):
    """Attestation is not configured, so no session can be issued.

    Distinct from a rejected token: nothing is wrong with the caller. It is a
    503 rather than a 500 so an operator reading logs sees a service state and
    not an unhandled crash, and distinct from 401 so it is never mistaken for a
    bad token. Either way no session is created.
    """

    status_code = 503
    default_code = "ATTESTATION_NOT_CONFIGURED"
    default_detail = (
        "App attestation is not configured on this server, so consumer sessions "
        "cannot be issued. Set APP_CHECK_PROJECT_NUMBER and "
        "APP_CHECK_ALLOWED_APP_IDS."
    )

SESSION_SCHEME = "Session"
APP_CHECK_HEADER = "HTTP_X_APP_CHECK"


class ConsumerSessionAuthentication(authentication.BaseAuthentication):
    """Authenticates the installation and attests the app.

    On success ``request.auth`` carries the ConsumerSession. ``request.user`` is
    left unauthenticated: there is no user here, and pretending otherwise would
    invite a staff permission check to pass by accident.
    """

    def authenticate(self, request):
        attestation = request.META.get(APP_CHECK_HEADER, "")
        try:
            app_id = get_attestation_verifier().verify(attestation)
        except AttestationFailed as exc:
            raise exceptions.AuthenticationFailed(
                {"code": "ATTESTATION_FAILED", "detail": str(exc)}
            ) from exc
        except NotImplementedError as exc:
            raise exceptions.AuthenticationFailed(
                {"code": "ATTESTATION_UNAVAILABLE", "detail": str(exc)}
            ) from exc
        except ImproperlyConfigured as exc:
            raise AttestationUnavailable(str(exc)) from exc

        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != SESSION_SCHEME:
            raise exceptions.AuthenticationFailed(
                {"code": "BAD_SESSION_HEADER", "detail": "expected 'Session <credential>'"}
            )

        session = sessions.resolve_session(parts[1])
        if session is None:
            raise exceptions.AuthenticationFailed(
                {"code": "SESSION_INVALID", "detail": "session expired or revoked"}
            )
        session.app_id = session.app_id or app_id
        return (None, session)

    def authenticate_header(self, request):
        return SESSION_SCHEME


class HasConsumerSession(permissions.BasePermission):
    """Requires a resolved consumer session on the request."""

    message = "A consumer session and app attestation are required."

    def has_permission(self, request, view) -> bool:
        from apps.verification.models import ConsumerSession

        return isinstance(request.auth, ConsumerSession)


class AttestedOnly(permissions.BasePermission):
    """Attestation without a session, for session creation itself."""

    message = "App attestation is required."

    def has_permission(self, request, view) -> bool:
        attestation = request.META.get(APP_CHECK_HEADER, "")
        try:
            get_attestation_verifier().verify(attestation)
        except (AttestationFailed, NotImplementedError):
            return False
        except ImproperlyConfigured as exc:
            # Surfaced rather than reported as a permission denial: the caller
            # did nothing wrong and the server cannot proceed.
            raise AttestationUnavailable(str(exc)) from exc
        return True
