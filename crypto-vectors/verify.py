#!/usr/bin/env python
"""Run the golden vectors against the Python implementation.

This is the reference runner. The Dart client and the OpenSSL CLI cross-check
must reach identical verdicts on the same files -- that agreement, not any one
library, is the interoperability contract.

Exit status is non-zero if any vector disagrees, so CI can gate on it.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from medcrypto.canonical import CanonicalisationError, parse_strict
from medcrypto.contexts import Context
from medcrypto.records import BindingError, check_activation_binding
from medcrypto.signing import verify_ok
from medcrypto.tokens import hash_token

HERE = Path(__file__).parent


def b64d(value: str) -> bytes:
    return base64.b64decode(value)


def context_by_value(value: str) -> Context:
    for member in Context:
        if member.value.decode() == value:
            return member
    raise ValueError(f"unknown context: {value}")


def run_signature_vector(vector: dict) -> bool:
    """Return True when the vector's actual result matches its expectation."""
    ok = verify_ok(
        b64d(vector["public_key"]),
        context_by_value(vector["context"]),
        b64d(vector["payload"]),
        b64d(vector["signature"]),
    )
    return ok is (vector["expected"] == "VALID")


def run_parse_vector(vector: dict) -> bool:
    try:
        parse_strict(b64d(vector["payload"]))
    except CanonicalisationError:
        return vector["expected"] == "INVALID"
    return vector["expected"] == "VALID"


def run_binding_vector(vector: dict) -> bool:
    """A binding vector must verify cryptographically and still be rejected."""
    payload = b64d(vector["payload"])
    signature_ok = verify_ok(
        b64d(vector["public_key"]),
        context_by_value(vector["context"]),
        payload,
        b64d(vector["signature"]),
    )
    if not signature_ok:
        # The point of this vector is that a *genuine* signature is refused on
        # binding grounds; a signature failure would test nothing.
        print("      note: signature unexpectedly failed, binding untested")
        return False
    try:
        check_activation_binding(
            payload,
            expected_token_sha256=hash_token(vector["presented_with_token"]),
            expected_manufacturer_id="mfr-square-pharmaceuticals",
            expected_key_id=vector["key_id"],
        )
    except BindingError:
        return vector["expected"] == "INVALID"
    return vector["expected"] == "VALID"


def main() -> int:
    files = sorted(HERE.glob("*/*.json"))
    if not files:
        print("no vectors found; run generate.py first")
        return 1

    failures = 0
    for path in files:
        vector = json.loads(path.read_text())
        check = vector.get("check", "signature")
        runner = {
            "signature": run_signature_vector,
            "parse": run_parse_vector,
            "binding": run_binding_vector,
        }[check]
        passed = runner(vector)
        status = "ok  " if passed else "FAIL"
        rel = path.relative_to(HERE)
        print(f"  [{status}] {rel}  ({check}, expect {vector['expected']})")
        if not passed:
            failures += 1

    print()
    if failures:
        print(f"{failures} of {len(files)} vectors FAILED")
        return 1
    print(f"all {len(files)} vectors passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
