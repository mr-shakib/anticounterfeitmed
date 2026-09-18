"""HTTP transport for the signing service.

One endpoint, one job: take finished canonical bytes and return a signature.
It does not build records, does not parse them, and has no database or object
storage access.

Two controls guard it, and both are required:

* the deployment puts it on an internal network with no public route, and the
  reverse proxy in front of it terminates mTLS;
* every request carries a shared bearer token, so a process that reaches the
  network is still not automatically able to sign.

Nothing here logs a payload or a signature. A caller's key id is logged because
it is needed to investigate misuse and is not secret.
"""

from __future__ import annotations

import base64
import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from medsigner.keystore import KeyNotAvailable, KeyStore
from medsigner.service import SigningService, UnknownContext

logger = logging.getLogger("medsigner")

MAX_PAYLOAD_BYTES = 64 * 1024


class SignRequest(BaseModel):
    key_id: str = Field(max_length=80)
    context: str = Field(max_length=64)
    payload_b64: str = Field(max_length=MAX_PAYLOAD_BYTES * 2)


class SignResponse(BaseModel):
    signature_b64: str
    key_id: str


class GenerateKeyResponse(BaseModel):
    key_id: str
    public_key_b64: str
    algorithm: str


def create_app(
    keystore_path: str | None = None,
    auth_token: str | None = None,
) -> FastAPI:
    path = keystore_path or os.environ.get("SIGNER_KEYSTORE_PATH", "/keys")
    token = auth_token if auth_token is not None else os.environ.get("SIGNER_AUTH_TOKEN", "")
    if not token:
        raise RuntimeError(
            "SIGNER_AUTH_TOKEN is required. The signing service must not accept "
            "unauthenticated requests even on an internal network."
        )

    service = SigningService(KeyStore(path))
    app = FastAPI(title="medsigner", docs_url=None, redoc_url=None, openapi_url=None)

    def _authorise(authorization: str | None) -> None:
        expected = f"Bearer {token}"
        # Constant-time comparison: the token is a secret, and a timing signal
        # would leak it to anything that can reach the port.
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="unauthorised")

    @app.get("/healthz")
    def healthz() -> dict:
        # Deliberately says nothing about which keys are present.
        return {"status": "ok"}

    @app.post("/keys", response_model=GenerateKeyResponse)
    def generate_key(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> GenerateKeyResponse:
        """Create a key pair inside this service and return only its public half.

        Generation belongs here rather than in the application: a key generated
        elsewhere would exist, however briefly, in a process that is supposed
        never to hold one. The private seed is written to the keystore and is
        not returned, logged, or recoverable through this API.
        """
        _authorise(authorization)

        from medcrypto.keys import ALGORITHM, generate_keypair

        pair = generate_keypair()
        service.keystore.store_seed(pair.key_id, pair.private_seed)
        logger.info("generated key key_id=%s", pair.key_id)
        return GenerateKeyResponse(
            key_id=pair.key_id,
            public_key_b64=base64.b64encode(pair.public_key).decode("ascii"),
            algorithm=ALGORITHM,
        )

    @app.post("/sign", response_model=SignResponse)
    def sign(
        body: SignRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> SignResponse:
        _authorise(authorization)

        try:
            payload = base64.b64decode(body.payload_b64, validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="payload is not base64") from exc

        if not payload:
            raise HTTPException(status_code=400, detail="empty payload")
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="payload too large")

        try:
            signature = service.sign(
                key_id=body.key_id, context=body.context, payload=payload
            )
        except UnknownContext as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyNotAvailable as exc:
            # Same status for "no such key" and "malformed key id": the caller
            # learns nothing about which keys this service holds.
            raise HTTPException(status_code=404, detail="key not available") from exc

        # Key id only. The payload and the signature never reach a log line.
        logger.info("signed request key_id=%s context=%s", body.key_id, body.context)
        return SignResponse(
            signature_b64=base64.b64encode(signature).decode("ascii"),
            key_id=body.key_id,
        )

    return app
