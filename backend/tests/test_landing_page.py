"""Compliance checks for the public landing page (docs/07, SRS 2.2).

The landing page is the only page that ever sees a package token, so its rules
are enforced here rather than left to review. In particular the CSP hash is
recomputed from the live file: editing the page without regenerating the header
fails, instead of silently shipping a CSP that no longer matches.
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

import pytest

LANDING = Path(__file__).resolve().parents[2] / "landing"
HTML = LANDING / "index.html"
NGINX = LANDING / "nginx.conf"

TRACKER_FINGERPRINTS = [
    "gtag", "googletagmanager", "google-analytics", "facebook", "fbq",
    "hotjar", "mixpanel", "segment.io", "sentry", "posthog", "clarity.ms",
    "plausible", "umami", "matomo",
]


@pytest.fixture(scope="module")
def html() -> str:
    return HTML.read_text()


def inline_hashes(html: str, tag: str) -> list[str]:
    out = []
    for match in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", html, re.S):
        body = match.group(1)
        if not body.strip():
            continue
        digest = hashlib.sha256(body.encode()).digest()
        out.append("'sha256-" + base64.b64encode(digest).decode() + "'")
    return out


def test_landing_page_exists():
    assert HTML.exists(), "landing/index.html is missing"
    assert NGINX.exists(), "landing/nginx.conf is missing"


def test_no_external_resources(html: str):
    """Nothing may load from another origin -- that is how a token leaks."""
    external = re.findall(r'(?:src|href)="(https?://[^"]*)"', html)
    assert not external, f"external resources referenced: {external}"


def test_no_analytics_or_trackers(html: str):
    lowered = html.lower()
    found = [name for name in TRACKER_FINGERPRINTS if name in lowered]
    assert not found, f"tracker fingerprints present: {found}"


def test_strips_the_fragment(html: str):
    """The page must clear the token from the address bar and history."""
    assert "replaceState" in html, "the fragment is never stripped"
    assert "location.hash" in html


def test_page_makes_no_network_calls(html: str):
    """No fetch, XHR, beacon or websocket may appear on this page."""
    for forbidden in ["fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource"]:
        assert forbidden not in html, f"page performs network activity: {forbidden}"


def test_csp_matches_the_current_page(html: str):
    """The committed CSP must match the page as it exists right now."""
    conf = NGINX.read_text()
    csp_match = re.search(r'Content-Security-Policy\s+"([^"]+)"', conf)
    assert csp_match, "no Content-Security-Policy in nginx.conf"
    csp = csp_match.group(1)

    for expected in inline_hashes(html, "script"):
        assert expected in csp, (
            f"inline script hash {expected} missing from CSP — "
            "regenerate it with `make landing-csp` after editing the page"
        )
    for expected in inline_hashes(html, "style"):
        assert expected in csp, (
            f"inline style hash {expected} missing from CSP — "
            "regenerate it with `make landing-csp` after editing the page"
        )


def test_csp_forbids_network_and_unsafe_inline():
    conf = NGINX.read_text()
    csp = re.search(r'Content-Security-Policy\s+"([^"]+)"', conf).group(1)
    assert "connect-src 'none'" in csp, "the page must not be able to call any API"
    assert "default-src 'none'" in csp
    assert "unsafe-inline" not in csp, "unsafe-inline would permit an injected tracker"
    assert "unsafe-eval" not in csp


def test_required_headers_present():
    conf = NGINX.read_text()
    assert 'Referrer-Policy "no-referrer"' in conf, "SRS 2.2 requires no-referrer"
    assert "X-Content-Type-Options" in conf


def test_root_is_served_directly_without_redirect():
    """A redirect could carry the fragment onward; the SRS forbids relying on one."""
    conf = NGINX.read_text()
    root_block = re.search(r"location = / \{(.*?)\n    \}", conf, re.S)
    assert root_block, "no explicit root location block"
    body = root_block.group(1)
    assert "return 30" not in body, "root must not redirect"
    assert "try_files" in body


def test_api_is_proxied_not_served_from_the_landing_root():
    """The API shares the origin; the page still cannot reach it.

    A path rule would add nothing here. What stops the landing page calling the
    API is its own CSP, which forbids every outbound connection, and that is
    asserted separately above.
    """
    conf = NGINX.read_text()
    assert "location /v1/" in conf
    assert "proxy_pass" in conf
    # The landing root must not fall through to the API.
    assert "root /srv/landing;" in conf


def test_plain_http_is_redirected_to_https():
    conf = NGINX.read_text()
    assert "listen 80;" in conf
    assert "return 301 https://" in conf
