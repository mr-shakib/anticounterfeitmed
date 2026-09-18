"""The isolated signing service and the backend's client for it.

These run the real HTTP transport against a real instance of the service, so
the isolation boundary is exercised rather than assumed.
"""

from __future__ import annotations

import base64
import threading
from pathlib import Path

import pytest
import uvicorn

from apps.trust.signing import RemoteSigner, SignerUnavailable
from medcrypto import canonicalise, generate_keypair
from medcrypto.contexts import Context
from medcrypto.signing import verify, verify_ok
from medsigner import KeyStore
from medsigner.server import create_app

AUTH_TOKEN = "test-signer-token"


@pytest.fixture(scope="module")
def signing_key(tmp_path_factory):
    keys = tmp_path_factory.mktemp("signer-keys")
    pair = generate_keypair()
    KeyStore(keys).store_seed(pair.key_id, pair.private_seed)
    return pair, keys


@pytest.fixture(scope="module")
def live_signer(signing_key):
    """Run the service on a real port for the duration of the module."""
    _pair, keys = signing_key
    app = create_app(keystore_path=str(keys), auth_token=AUTH_TOKEN)
    config = uvicorn.Config(app, host="127.0.0.1", port=8911, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    import time

    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "signing service did not start"

    yield "http://127.0.0.1:8911"

    server.should_exit = True
    thread.join(timeout=5)


def client(url: str, token: str = AUTH_TOKEN) -> RemoteSigner:
    return RemoteSigner(url, auth_token=token)


def test_service_signs_and_the_signature_verifies(live_signer, signing_key):
    pair, _keys = signing_key
    payload = canonicalise({"schema": "medicine-activation-v1", "n": 1})

    signature = client(live_signer).sign(
        key_id=pair.key_id,
        context=Context.ACTIVATION.value.decode(),
        payload=payload,
    )

    assert len(signature) == 3309
    verify(pair.public_key, Context.ACTIVATION, payload, signature)


def test_context_separation_survives_the_transport(live_signer, signing_key):
    pair, _keys = signing_key
    payload = canonicalise({"a": 1})
    signature = client(live_signer).sign(
        key_id=pair.key_id,
        context=Context.ACTIVATION.value.decode(),
        payload=payload,
    )
    assert not verify_ok(pair.public_key, Context.STATUS, payload, signature)


def test_requests_without_the_token_are_refused(live_signer, signing_key):
    pair, _keys = signing_key
    with pytest.raises(SignerUnavailable):
        client(live_signer, token="wrong-token").sign(
            key_id=pair.key_id,
            context=Context.ACTIVATION.value.decode(),
            payload=canonicalise({"a": 1}),
        )


def test_unknown_key_is_refused_without_revealing_which_keys_exist(live_signer):
    with pytest.raises(SignerUnavailable):
        client(live_signer).sign(
            key_id="mldsa65-" + "0" * 32,
            context=Context.ACTIVATION.value.decode(),
            payload=canonicalise({"a": 1}),
        )


def test_a_malformed_key_id_cannot_escape_the_keystore(live_signer):
    """A key id arrives over the wire, so it must never be a path component."""
    for bad in ["../../etc/passwd", "mldsa65-../secret", "", "not-a-key-id"]:
        with pytest.raises(SignerUnavailable):
            client(live_signer).sign(
                key_id=bad,
                context=Context.ACTIVATION.value.decode(),
                payload=canonicalise({"a": 1}),
            )


def test_an_unrecognised_context_is_refused(live_signer, signing_key):
    """A caller cannot invent a record type and have an existing key sign it."""
    pair, _keys = signing_key
    with pytest.raises(SignerUnavailable):
        client(live_signer).sign(
            key_id=pair.key_id,
            context="medicine-something-invented-v1",
            payload=canonicalise({"a": 1}),
        )


def test_empty_payload_is_refused(live_signer, signing_key):
    pair, _keys = signing_key
    with pytest.raises(SignerUnavailable):
        client(live_signer).sign(
            key_id=pair.key_id,
            context=Context.ACTIVATION.value.decode(),
            payload=b"",
        )


def test_unreachable_service_raises_signer_unavailable(signing_key):
    """An activation run must see a per-unit failure, not a transport error."""
    pair, _keys = signing_key
    with pytest.raises(SignerUnavailable, match="unreachable"):
        client("http://127.0.0.1:9").sign(
            key_id=pair.key_id,
            context=Context.ACTIVATION.value.decode(),
            payload=canonicalise({"a": 1}),
        )


def test_service_refuses_to_start_without_a_token(tmp_path):
    """Unauthenticated signing must not be reachable even by misconfiguration."""
    with pytest.raises(RuntimeError, match="SIGNER_AUTH_TOKEN"):
        create_app(keystore_path=str(tmp_path), auth_token="")


def test_client_refuses_to_be_built_without_a_token():
    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured):
        RemoteSigner("http://signer:9000", auth_token="")


def test_signer_never_logs_a_payload(live_signer, signing_key, caplog):
    pair, _keys = signing_key
    payload = canonicalise({"secret_marker": "must-not-appear-in-logs"})
    with caplog.at_level("INFO"):
        client(live_signer).sign(
            key_id=pair.key_id,
            context=Context.ACTIVATION.value.decode(),
            payload=payload,
        )
    assert "must-not-appear-in-logs" not in caplog.text
    assert base64.b64encode(payload).decode() not in caplog.text


def test_keys_are_generated_inside_the_service(live_signer, tmp_path):
    """The application must never hold a private seed, in any mode.

    Generation happens in the signing service and only the public half comes
    back, so a key cannot exist in a process that is supposed never to have one.
    """
    generated = client(live_signer).generate_key()

    assert generated.key_id.startswith("mldsa65-")
    assert len(generated.public_key) == 1952

    # The returned key really is usable for verification, and the private half
    # is only reachable by asking the service to sign.
    payload = canonicalise({"schema": "medicine-activation-v1"})
    signature = client(live_signer).sign(
        key_id=generated.key_id,
        context=Context.ACTIVATION.value.decode(),
        payload=payload,
    )
    verify(generated.public_key, Context.ACTIVATION, payload, signature)


def test_key_generation_requires_the_token(live_signer):
    with pytest.raises(SignerUnavailable):
        client(live_signer, token="wrong-token").generate_key()


@pytest.mark.django_db
def test_provisioning_records_only_the_public_half(live_signer, settings, monkeypatch):
    """A provisioned key row must carry a reference, never key material."""
    from apps.trust.models import KeyPurpose, SigningKey
    from apps.trust.services import provision_signing_key

    settings.SIGNER_MODE = "service"
    settings.SIGNER_URL = live_signer
    settings.SIGNER_AUTH_TOKEN = AUTH_TOKEN

    key = provision_signing_key(purpose=KeyPurpose.STATUS)

    stored = SigningKey.objects.get(pk=key.pk)
    assert len(bytes(stored.public_key)) == 1952
    assert stored.private_key_reference == f"keystore:{stored.key_id}"
    # Nothing on the row is a 32-byte seed or anything like one.
    assert "seed" not in stored.private_key_reference.lower()
