"""Per-session rate limits.

Pilot starting values from docs/05. They are tuned against real networks, not
treated as fixed: broader IP controls in particular must tolerate many genuine
users behind one NAT, which is normal on shared pharmacy and mobile networks.

A rate-limit failure is an abuse signal at most. It is never a counterfeit
label, and nothing here may change a unit's state.
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class _SessionScopedThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        session = getattr(request, "auth", None)
        if session is None:
            return None  # unauthenticated requests are rejected before this
        return self.cache_format % {"scope": self.scope, "ident": str(session.id)}


class PrepareThrottle(_SessionScopedThrottle):
    scope = "consumer_prepare"


class ConfirmThrottle(_SessionScopedThrottle):
    scope = "consumer_confirm"
