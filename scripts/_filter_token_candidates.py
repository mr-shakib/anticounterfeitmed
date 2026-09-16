#!/usr/bin/env python
"""Filter grep hits down to strings that plausibly are real tokens.

Reads grep output on stdin. Exits non-zero if any candidate survives.
"""

from __future__ import annotations

import re
import sys

CANDIDATE = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])")


def looks_random(value: str) -> bool:
    """A real token is random, so it carries both cases.

    Identifiers are snake_case or SCREAMING_CASE and fail this; a genuine token
    fails it with probability about 4e-10.
    """
    return any(c.isupper() for c in value) and any(c.islower() for c in value)


def main() -> int:
    findings = []
    for line in sys.stdin:
        for match in CANDIDATE.finditer(line):
            value = match.group(1)
            if looks_random(value):
                findings.append((line.rstrip(), value))

    if findings:
        print("Possible raw token committed:")
        for line, value in findings:
            print(f"  {line}")
            print(f"    -> candidate: {value}")
        print()
        print("Tokens must never be stored or committed. Only SHA-256 digests persist.")
        return 1

    print("no raw tokens found outside crypto-vectors/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
