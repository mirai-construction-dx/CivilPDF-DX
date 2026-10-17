"""Lightweight in-memory rate limiting for sensitive auth endpoints.

Protects the login / token / password-reset surface against credential
stuffing and token-abuse bursts before the account-level lockout (5 failures /
15 minutes) kicks in. Limits are per client IP and held in process memory —
adequate for the single- or few-worker MVP deployment documented in
docs/deployment/docker-production-deployment.md.

For multi-worker / horizontal deployments move this to a shared store
(Redis is already a declared dependency) before scaling out.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from config import settings

# Path -> (max_requests, window_seconds). More specific prefixes win.
_RULES: dict[str, tuple[int, int]] = {
    "/api/v1/integration/ping": (60, 60),
    "/api/v1/integration/catalog": (120, 60),
    "/api/v1/auth/token": (10, 60),
    "/api/v1/auth/m365/login": (10, 60),
    "/api/v1/auth/password-reset/request": (5, 60),
    "/api/v1/auth/refresh": (30, 60),
}
_ACTIVE_INSTANCES: list["RateLimitMiddleware"] = []


def reset_all() -> None:
    """Clear in-memory counters for every live instance (used by tests)."""
    for instance in _ACTIVE_INSTANCES:
        instance._hits.clear()


def _client_ip(request: Request) -> str:
    """Resolve the client IP, honoring proxy headers only when explicitly trusted."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-IP limiter with an injectable clock for tests."""

    def __init__(
        self,
        app: ASGIApp,
        clock: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(app)
        self._clock = clock or time.monotonic
        self._hits: dict[str, dict[str, deque[float]]] = defaultdict(
            lambda: defaultdict(deque)
        )
        _ACTIVE_INSTANCES.append(self)

    @staticmethod
    def _match(path: str) -> tuple[int, int] | None:
        for prefix, rule in _RULES.items():
            if path.startswith(prefix):
                return rule
        return None

    def _check(self, key: str, path: str) -> tuple[bool, int]:
        rule = self._match(path)
        if rule is None:
            return True, 0
        limit, window = rule
        now = self._clock()
        bucket = self._hits[key][path]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(bucket[0] + window - now) + 1
            return False, retry_after
        bucket.append(now)
        return True, 0

    async def dispatch(self, request: Request, call_next) -> Response:
        ip = _client_ip(request)
        allowed, retry_after = self._check(ip, request.url.path)
        if not allowed:
            response = Response(
                status_code=429,
                content='{"detail":"Too many requests"}',
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )
            return response
        return await call_next(request)
