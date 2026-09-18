"""Consumer API endpoints.

Two conventions run through this module.

First, a verification outcome is never an HTTP error. An unknown token, an
expired batch or a recall all return 200 with a signed envelope, so the app can
verify the signature on a negative answer exactly as it does on a positive one.
HTTP errors are reserved for transport and authorization problems.

Second, nothing here decides an outcome. The services layer does that inside a
transaction; these views marshal input, call it, and sign the result.
"""

from __future__ import annotations

import base64

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.trust.models import TrustManifest
from apps.verification import sessions as session_service
from apps.verification.authentication import (
    AttestedOnly,
    ConsumerSessionAuthentication,
    HasConsumerSession,
)
from apps.verification.envelopes import sign_status
from apps.verification.models import VerificationOutcome
from apps.verification.serializers import (
    ConfirmSerializer,
    OperationStatusSerializer,
    PackageStatusSerializer,
    PrepareSerializer,
    ReportCreateSerializer,
    SessionCreateSerializer,
)
from apps.verification.services import (
    ChallengeInvalid,
    IdempotencyConflict,
    confirm_verification,
    prepare_verification,
)
from apps.verification.throttling import ConfirmThrottle, PrepareThrottle

CONSUMER_AUTH = [ConsumerSessionAuthentication]


def _b64(raw: bytes | None) -> str | None:
    return base64.b64encode(raw).decode("ascii") if raw else None


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AttestedOnly])
def create_session(request):
    """Create an anonymous session, only after attestation has passed."""
    serializer = SessionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    issued = session_service.create_session(
        installation_id=serializer.validated_data.get("installation_id", "")
    )
    return Response(
        {
            # Returned exactly once. It is not recoverable afterwards.
            "session_credential": issued.credential,
            "expires_at": issued.session.expires_at.isoformat(),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def trust_manifest(request):
    """The current root-signed manifest of keys the app may trust."""
    manifest = TrustManifest.objects.order_by("-version").first()
    if manifest is None:
        return Response(
            {"code": "NO_MANIFEST", "detail": "no trust manifest has been published"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(
        {
            "version": manifest.version,
            "payload": _b64(bytes(manifest.canonical_bytes)),
            "signature": _b64(bytes(manifest.signature)),
            "key_id": manifest.signed_by.key_id,
            "algorithm": "ML-DSA-65",
        }
    )


@api_view(["POST"])
@authentication_classes(CONSUMER_AUTH)
@permission_classes([HasConsumerSession])
@throttle_classes([PrepareThrottle])
def prepare(request):
    """Look up a scanned token and, when eligible, issue a challenge.

    This never redeems. The unit's state is unchanged by calling it.
    """
    serializer = PrepareSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token = serializer.validated_data["token"]
    nonce = serializer.validated_data["nonce"]

    result = prepare_verification(session=request.auth, token=token)

    credential_digest = None
    if result.credential_bytes is not None:
        from medcrypto.records import credential_digest as digest_of

        credential_digest = digest_of(result.credential_bytes)

    envelope = sign_status(
        unit=result.unit,
        outcome=result.outcome,
        restrictions=result.restrictions,
        request_nonce=nonce,
        credential_digest=credential_digest,
    )

    body = {
        "outcome": result.outcome,
        "status": envelope.as_response(),
        "challenge_id": str(result.challenge.id) if result.challenge else None,
        "challenge_expires_at": (
            result.challenge.expires_at.isoformat() if result.challenge else None
        ),
        "unit_id": str(result.unit.id) if result.unit else None,
        "activation_credential": (
            {
                "payload": _b64(result.credential_bytes),
                "signature": _b64(result.credential_signature),
                "key_id": result.credential_key_id,
                "algorithm": "ML-DSA-65",
            }
            if result.credential_bytes
            else None
        ),
    }
    return Response(body)


@api_view(["POST"])
@authentication_classes(CONSUMER_AUTH)
@permission_classes([HasConsumerSession])
@throttle_classes([ConfirmThrottle])
def confirm(request):
    """Commit a first verification or a repeat check, idempotently."""
    serializer = ConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    body = {
        "unit_id": str(data["unit_id"]),
        "challenge_id": str(data["challenge_id"]),
    }

    try:
        result = confirm_verification(
            session=request.auth,
            unit_id=data["unit_id"],
            challenge_id=data["challenge_id"],
            idempotency_key=data["idempotency_key"],
            body=body,
        )
    except IdempotencyConflict as exc:
        return Response(
            {"code": "IDEMPOTENCY_CONFLICT", "detail": str(exc)},
            status=status.HTTP_409_CONFLICT,
        )
    except ChallengeInvalid as exc:
        return Response(
            {"code": "CHALLENGE_INVALID", "detail": str(exc)},
            status=status.HTTP_409_CONFLICT,
        )

    unit = result.operation.unit
    credential = getattr(unit, "activation_credential", None)

    envelope = sign_status(
        unit=unit,
        outcome=result.outcome,
        restrictions=result.event.detail.get("restrictions", []) if result.event else [],
        request_nonce=data["nonce"],
        credential_digest=credential.credential_digest if credential else None,
        operation_id=str(result.operation.id),
        event_id=str(result.event.id) if result.event else None,
    )

    return Response(
        {
            "outcome": result.outcome,
            "first_verification_recorded": result.first_redemption,
            "operation_id": str(result.operation.id),
            "replayed": result.replayed,
            # The event is committed either way. This only says whether the
            # signed receipt is available yet, so the app can poll rather than
            # implying the verification did not happen.
            "receipt_ready": result.operation.receipt_ready,
            "status": envelope.as_response(),
        }
    )


@api_view(["POST"])
@authentication_classes(CONSUMER_AUTH)
@permission_classes([HasConsumerSession])
def operation_status(request, operation_id):
    """Recover the result of an earlier attempt. Records no new check.

    Used when a confirmation committed but its response never arrived.
    """
    serializer = OperationStatusSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    from apps.verification.models import VerificationOperation

    operation = VerificationOperation.objects.filter(
        pk=operation_id, session=request.auth
    ).first()
    if operation is None:
        # Scoped to the owning session, so one installation cannot read
        # another's operations.
        return Response(
            {"code": "NOT_FOUND", "detail": "no such operation for this session"},
            status=status.HTTP_404_NOT_FOUND,
        )

    unit = operation.unit
    credential = getattr(unit, "activation_credential", None) if unit else None
    envelope = sign_status(
        unit=unit,
        outcome=operation.outcome,
        restrictions=[],
        request_nonce=serializer.validated_data["nonce"],
        credential_digest=credential.credential_digest if credential else None,
        operation_id=str(operation.id),
        event_id=str(operation.event_id) if operation.event_id else None,
    )
    return Response(
        {
            "outcome": operation.outcome,
            "operation_id": str(operation.id),
            "receipt_ready": operation.receipt_ready,
            "status": envelope.as_response(),
        }
    )


@api_view(["POST"])
@authentication_classes(CONSUMER_AUTH)
@permission_classes([HasConsumerSession])
@throttle_classes([PrepareThrottle])
def package_status(request):
    """Refresh a known package's status without redeeming it.

    An old receipt cannot establish today's recall or redemption status, so the
    app calls this rather than trusting what it stored.
    """
    serializer = PackageStatusSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    from medcrypto.tokens import hash_token, is_well_formed_token

    from apps.serialization.models import PackageUnit

    token = serializer.validated_data["token"]
    unit = None
    if is_well_formed_token(token):
        unit = PackageUnit.objects.select_related("batch__product__manufacturer").filter(
            token_sha256=hash_token(token)
        ).first()

    if unit is None:
        envelope = sign_status(
            unit=None,
            outcome=VerificationOutcome.NOT_FOUND,
            restrictions=[],
            request_nonce=serializer.validated_data["nonce"],
        )
        return Response({"outcome": VerificationOutcome.NOT_FOUND,
                         "status": envelope.as_response()})

    from django.utils import timezone

    from apps.verification.services import _active_restrictions, _outcome_for_restrictions

    restrictions = _active_restrictions(
        unit.batch.product.manufacturer, unit.batch, unit, timezone.now()
    )
    if restrictions:
        outcome = _outcome_for_restrictions(restrictions)
    elif unit.lifecycle == "REDEEMED":
        outcome = VerificationOutcome.PREVIOUSLY_VERIFIED
    elif unit.lifecycle == "ACTIVE":
        outcome = VerificationOutcome.VERIFIED_FIRST
    else:
        outcome = VerificationOutcome.NOT_ACTIVATED

    credential = getattr(unit, "activation_credential", None)
    envelope = sign_status(
        unit=unit,
        outcome=outcome,
        restrictions=restrictions,
        request_nonce=serializer.validated_data["nonce"],
        credential_digest=credential.credential_digest if credential else None,
    )
    return Response({"outcome": outcome, "status": envelope.as_response()})


@api_view(["POST"])
@authentication_classes(CONSUMER_AUTH)
@permission_classes([HasConsumerSession])
def create_report(request):
    """File a concern report.

    A token is optional: a consumer whose code will not scan still needs a way
    to raise a concern, so an external reference or typed batch number is
    accepted instead.
    """
    serializer = ReportCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    from medcrypto.tokens import hash_token, is_well_formed_token

    from apps.reports.models import Report
    from apps.serialization.models import PackageUnit

    unit = None
    token = data.get("token") or ""
    if token and is_well_formed_token(token):
        unit = PackageUnit.objects.filter(token_sha256=hash_token(token)).first()

    with transaction.atomic():
        report = Report.objects.create(
            case_number=_next_case_number(),
            reason=data["reason"],
            description=data.get("description", ""),
            unit=unit,
            external_reference=data.get("external_reference", ""),
            batch_number_text=data.get("batch_number_text", ""),
            reporter_session=request.auth,
            pharmacy_note=data.get("pharmacy_note", ""),
            organization=unit.batch.product.manufacturer if unit else None,
        )

    return Response(
        {"case_number": report.case_number, "status": report.status},
        status=status.HTTP_201_CREATED,
    )


def _next_case_number() -> str:
    import secrets as _secrets

    return "CASE-" + _secrets.token_hex(4).upper()
