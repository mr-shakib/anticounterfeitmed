#!/usr/bin/env python
"""Verify that activation credentials in a restored database still check out.

A restore that returns rows but not verifiable signatures is not a recovery.
This reads the credentials straight out of the restored database -- no Django,
no application code -- and checks each signature against the public key the
database says signed it, plus the token binding it claims.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg

from medcrypto.contexts import Context
from medcrypto.records import BindingError, check_activation_binding
from medcrypto.signing import verify_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="5432")
    parser.add_argument("--db", default="acm")
    parser.add_argument("--user", default="acm")
    args = parser.parse_args()

    conninfo = (
        f"host={args.host} port={args.port} dbname={args.db} user={args.user} "
        f"password={os.environ.get('PGPASSWORD', '')}"
    )

    checked = 0
    failures: list[str] = []

    with psycopg.connect(conninfo) as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.canonical_bytes, c.signature, k.public_key, k.key_id,
                   u.token_sha256, k.organization_id
            FROM activation_credential c
            JOIN signing_key k ON k.id = c.signing_key_id
            JOIN package_unit u ON u.id = c.unit_id
            """
        )
        for payload, signature, public_key, key_id, token_hash, org_id in cursor:
            checked += 1
            payload = bytes(payload)
            if not verify_ok(
                bytes(public_key), Context.ACTIVATION, payload, bytes(signature)
            ):
                failures.append(f"{key_id}: signature did not verify")
                continue
            try:
                check_activation_binding(
                    payload,
                    expected_token_sha256=bytes(token_hash),
                    expected_manufacturer_id=str(org_id),
                    expected_key_id=key_id,
                )
            except BindingError as exc:
                failures.append(f"{key_id}: {exc}")

    if checked == 0:
        print("  no activation credentials in this backup; nothing to verify")
        return 0

    for failure in failures:
        print(f"  FAIL {failure}", file=sys.stderr)
    if failures:
        print(f"  {len(failures)} of {checked} credentials failed", file=sys.stderr)
        return 1

    print(f"  all {checked} restored credentials verify and bind correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
