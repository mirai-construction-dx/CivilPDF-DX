"""Per-request context shared with code that has no access to the Request object.

The audit chain needs the client IP of the request that caused an audit entry
(requirements §5.4 ``ip_address``), but most routers call
``create_chained_audit_log(..., ip_address=None)`` because they never touch the
``Request``. ``AuditMiddleware`` stores the IP in a ContextVar for the duration
of the request, and ``create_chained_audit_log`` falls back to it when the
caller passed no explicit address.

Outside an HTTP request (scheduled retention / deletion jobs, CLI scripts) the
variable is unset and the audit entry keeps ``ip_address = None``.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

from starlette.requests import Request

from config import settings

_client_ip: ContextVar[Optional[str]] = ContextVar("civilpdf_client_ip", default=None)


def client_ip_from_request(request: Request) -> Optional[str]:
    """Return the client IP using the same rule as ``api.auth._client_ip``.

    ``X-Forwarded-For`` is honoured only when ``trust_proxy_headers`` is
    enabled; otherwise a client could forge its own audit IP.
    """
    if getattr(settings, "trust_proxy_headers", False):
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",", 1)[0].strip() if forwarded else ""
        if first:
            return first
    return request.client.host if request.client else None


def set_client_ip(ip: Optional[str]) -> Token:
    return _client_ip.set(ip)


def reset_client_ip(token: Token) -> None:
    _client_ip.reset(token)


def current_client_ip() -> Optional[str]:
    """IP of the HTTP request being handled, or None outside a request."""
    return _client_ip.get()
