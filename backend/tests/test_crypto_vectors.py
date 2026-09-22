"""The golden vectors run as part of the normal test suite.

Keeping them here means a dependency bump that changes signing behaviour fails
CI rather than being discovered on a device later.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from medcrypto import labels
from medcrypto.canonical import CanonicalisationError, parse_strict
from medcrypto.contexts import Context
from medcrypto.records import BindingError, check_activation_binding
from medcrypto.signing import verify_ok
from medcrypto.tokens import hash_token

VECTOR_DIR = Path(__file__).resolve().parents[2] / "crypto-vectors"
VECTORS = sorted(VECTOR_DIR.glob("*/*.json"))


def context_by_value(value: str) -> Context:
    for member in Context:
        if member.value.decode() == value:
            return member
    raise ValueError(f"unknown context: {value}")


def test_vectors_exist():
    assert VECTORS, "no golden vectors found; run crypto-vectors/generate.py"


@pytest.mark.parametrize("path", VECTORS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_vector(path: Path):
    vector = json.loads(path.read_text())
    expected_valid = vector["expected"] == "VALID"
    check = vector.get("check", "signature")

    if check == "parse":
        try:
            parse_strict(base64.b64decode(vector["payload"]))
        except CanonicalisationError:
            assert not expected_valid
        else:
            assert expected_valid
        return

    if check == "label":
        token = labels.token_from_data_codewords(
            bytes.fromhex(vector["data_codewords"]), text=vector["text"]
        )
        assert token == (vector["token"] if expected_valid else None)
        return

    signature_ok = verify_ok(
        base64.b64decode(vector["public_key"]),
        context_by_value(vector["context"]),
        base64.b64decode(vector["payload"]),
        base64.b64decode(vector["signature"]) if vector["signature"] else b"",
    )

    if check == "binding":
        # The signature must be genuine, so that the binding check is what
        # rejects it. A signature failure here would prove nothing.
        assert signature_ok, "binding vector must carry a valid signature"
        with pytest.raises(BindingError):
            check_activation_binding(
                base64.b64decode(vector["payload"]),
                expected_token_sha256=hash_token(vector["presented_with_token"]),
                expected_manufacturer_id="mfr-square-pharmaceuticals",
                expected_key_id=vector["key_id"],
            )
        return

    assert signature_ok is expected_valid
