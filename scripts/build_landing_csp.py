#!/usr/bin/env python
"""Recompute the landing page's CSP hashes into landing/nginx.conf.

Run after any edit to landing/index.html. The test suite fails if the committed
CSP no longer matches the page, so this is not optional housekeeping.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

LANDING = Path(__file__).resolve().parent.parent / "landing"


def inline_hashes(html: str, tag: str) -> list[str]:
    out = []
    for match in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.S):
        body = match.group(1)
        if body.strip():
            digest = hashlib.sha256(body.encode()).digest()
            out.append("'sha256-" + base64.b64encode(digest).decode() + "'")
    return out


def main() -> None:
    html = (LANDING / "index.html").read_text()
    csp = (
        "default-src 'none'; "
        f"script-src {' '.join(inline_hashes(html, 'script'))}; "
        f"style-src {' '.join(inline_hashes(html, 'style'))}; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'; connect-src 'none'"
    )
    conf_path = LANDING / "nginx.conf"
    conf = conf_path.read_text()
    updated = re.sub(
        r'(add_header Content-Security-Policy ")[^"]+(")',
        lambda m: m.group(1) + csp + m.group(2),
        conf,
    )
    conf_path.write_text(updated)
    (LANDING / "csp.txt").write_text(csp + "\n")
    print("CSP updated:\n" + csp)


if __name__ == "__main__":
    main()
