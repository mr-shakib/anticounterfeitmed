"""Rate limit for the print-line scan endpoint.

The endpoint takes raw tokens, so an unbounded one would let a signed-in staff
account test guesses. The limit is generous enough for a print line reading
labels one after another and far too slow to search a 32-byte space.

Exceeding it is an operational signal, never a counterfeit finding.
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class PrintScanThrottle(SimpleRateThrottle):
    scope = "staff_print_scan"

    def get_cache_key(self, request, view):
        membership = getattr(request, "membership", None)
        if membership is None:
            return None  # unauthenticated requests are rejected before this
        return self.cache_format % {"scope": self.scope, "ident": str(membership.id)}
