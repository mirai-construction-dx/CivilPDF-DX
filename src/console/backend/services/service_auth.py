"""Service-to-service authentication for the integration API.

ADR-0006 D-2: peers (e.g. Civil-Docs-Platform) call ``/api/v1/integration/*``
with an HMAC-signed request. Human JWT authentication is deliberately not used:
a machine consumer has no interactive session, and a leaked user token would
grant far more than one integration call.

Canonical signing string (UTF-8, LF-separated, no trailing newline)::

    METHOD
    PATH
    TIMESTAMP
    NONCE
    SHA256_HEX(BODY)

* ``METHOD`` — upper-case HTTP method.
* ``PATH`` — ``request.url.path`` (query strings are not part of the contract).
* ``TIMESTAMP`` — Unix epoch seconds (RFC 3339 is also accepted for convenience).
* ``NONCE`` — random 128-bit hex supplied by the caller.
* ``BODY`` — the raw request body (empty for GET).

Signature: ``hex(HMAC-SHA256(secret, canonical))`` in the ``X-CivilPDF-Signature``
header. Required headers: ``X-CivilPDF-System``, ``X-CivilPDF-Timestamp``,
``X-CivilPDF-Nonce``, ``X-CivilPDF-Signature``.

Secrets are configured per peer system as a JSON object in
``INTEGRATION_HMAC_SECRETS`` (e.g. ``{"civil-docs-platform":"<hex>"}``). When it is
unset the integration API returns 503 (fail closed) instead of accepting
unsigned calls.

Replay protection: a nonce is remembered for the clock-skew window and rejected
when reused. The cache is per process; with multiple uvicorn workers a replayed
request can reach another worker. Idempotency keys on the job API bound the
side effects, and a DB-backed nonce store is the follow-up hardening. This
limitation is documented in docs/api/integration-api.md.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status

from config import settings

SYSTEM_HEADER = "X-CivilPDF-System"
TIMESTAMP_HEADER = "X-CivilPDF-Timestamp"
NONCE_HEADER = "X-CivilPDF-Nonce"
SIGNATURE_HEADER = "X-CivilPDF-Signature"


@dataclass(frozen=True)
class ServiceIdentity:
    """The authenticated calling system."""

    system_id: str


_nonce_lock = threading.Lock()
_seen_nonces: dict[tuple[str, str], float] = {}


def reset_nonce_cache() -> None:
    """Clear the replay cache (tests and long-running workers)."""
    with _nonce_lock:
        _seen_nonces.clear()


def canonical_string(
    method: str, path: str, timestamp: str, nonce: str, body: bytes
) -> str:
    return (
        f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    )


def sign_request(
    secret: str, method: str, path: str, timestamp: str, nonce: str, body: bytes = b""
) -> str:
    """Return the hex signature for a request (also used by peers/tests)."""
    message = canonical_string(method, path, timestamp, nonce, body).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _parse_timestamp(value: str) -> float | None:
    """Accept Unix epoch seconds, or an RFC 3339 timestamp."""
    try:
        return float(int(value))
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _remember_nonce(system_id: str, nonce: str, now: float, window: float) -> bool:
    """Return False when the nonce was already used inside the window."""
    with _nonce_lock:
        for key, seen in list(_seen_nonces.items()):
            if now - seen > window:
                del _seen_nonces[key]
        key = (system_id, nonce)
        if key in _seen_nonces:
            return False
        _seen_nonces[key] = now
        return True


async def require_service(request: Request) -> ServiceIdentity:
    """FastAPI dependency: authenticate a signed service request.

    503 when the integration API has no secrets configured (fail closed),
    401 for every authentication failure.
    """
    secrets = settings.integration_hmac_secrets or {}
    if not secrets:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="integration API is not configured",
        )

    system_id = request.headers.get(SYSTEM_HEADER, "")
    timestamp = request.headers.get(TIMESTAMP_HEADER, "")
    nonce = request.headers.get(NONCE_HEADER, "")
    signature = request.headers.get(SIGNATURE_HEADER, "")
    if not all((system_id, timestamp, nonce, signature)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing service authentication headers",
        )

    secret = secrets.get(system_id)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unknown calling system",
        )

    parsed_timestamp = _parse_timestamp(timestamp)
    window = float(settings.integration_clock_skew_seconds)
    now = time.time()
    if parsed_timestamp is None or abs(now - parsed_timestamp) > window:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="timestamp outside the allowed clock skew",
        )

    body = await request.body()
    expected = sign_request(
        secret, request.method, request.url.path, timestamp, nonce, body
    )
    if not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid signature",
        )

    if not _remember_nonce(system_id, nonce, now, window):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="replayed nonce",
        )

    return ServiceIdentity(system_id=system_id)
