"""HMAC v1 service authentication, disabled without peer secrets and shared Redis.

Canonical UTF-8 input (LF-separated, no trailing LF):
SYSTEM, METHOD, PATH, TIMESTAMP, NONCE, SHA256_HEX(BODY).
Query strings are rejected. TIMESTAMP is Unix epoch seconds; NONCE is 32 hex
characters. Redis atomically retains nonces through the complete signature
validity interval, with a fixed per-peer bound. No process-local fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from redis import asyncio as redis
from redis.exceptions import RedisError

from config import settings

SYSTEM_HEADER = "X-CivilPDF-System"
TIMESTAMP_HEADER = "X-CivilPDF-Timestamp"
NONCE_HEADER = "X-CivilPDF-Nonce"
SIGNATURE_HEADER = "X-CivilPDF-Signature"
MAX_NONCES_PER_PEER = 1000
MAX_BODY_BYTES = 4096

# Sorted-set member expiry uses signed time, not arrival time: a future-dated
# signature must remain consumed until timestamp + skew has passed.
_NONCE_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZSCORE', KEYS[1], ARGV[2]) then return 0 end
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[4]) then return -1 end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""


@dataclass(frozen=True)
class ServiceIdentity:
    system_id: str


def sign_request(
    secret: str,
    system_id: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes = b"",
) -> str:
    canonical = (
        f"{system_id}\n{method.upper()}\n{path}\n{timestamp}\n{nonce}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    )
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


async def _consume_nonce(
    system_id: str, nonce: str, now: float, expires: float, window: int
) -> int:
    """1 accepted, 0 replay, -1 quota. Redis failure never authenticates."""
    # Do not put caller-controlled plaintext into shared Redis key names.
    peer = hashlib.sha256(system_id.encode()).hexdigest()
    async with redis.from_url(
        settings.integration_nonce_redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    ) as store:
        result = await store.eval(
            _NONCE_SCRIPT,
            1,
            f"civilpdf:integration:nonce:v1:{peer}",
            now,
            nonce,
            expires,
            MAX_NONCES_PER_PEER,
            math.ceil(2 * window + 2),
        )
    return int(result)


async def require_service(request: Request) -> ServiceIdentity:
    """Authenticate service calls only; the read-only catalog stays public."""
    secrets = settings.integration_hmac_secrets
    if not secrets or not settings.integration_nonce_redis_url:
        raise HTTPException(503, "integration API is not configured")

    system_id = request.headers.get(SYSTEM_HEADER, "")
    timestamp = request.headers.get(TIMESTAMP_HEADER, "")
    nonce = request.headers.get(NONCE_HEADER, "")
    signature = request.headers.get(SIGNATURE_HEADER, "")
    if (
        not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", system_id)
        or not re.fullmatch(r"[0-9]{1,12}", timestamp)
        or not re.fullmatch(r"[0-9a-f]{32}", nonce)
        or not re.fullmatch(r"[0-9a-f]{64}", signature)
    ):
        raise HTTPException(401, "invalid service authentication headers")
    secret = secrets.get(system_id)
    if not secret:
        raise HTTPException(401, "unknown calling system")
    now = time.time()
    window = settings.integration_clock_skew_seconds
    signed_time = int(timestamp)
    if abs(now - signed_time) > window:
        raise HTTPException(401, "timestamp outside the allowed clock skew")
    if request.url.query:
        raise HTTPException(400, "query strings are not supported")

    # Even a valid peer header must never allow unauthenticated unbounded reads.
    # GET/ping has no body at all; other methods are reserved for future APIs.
    limit = 0 if request.method == "GET" else MAX_BODY_BYTES
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "service request body too large")
        body.extend(chunk)
    expected = sign_request(
        secret,
        system_id,
        request.method,
        request.url.path,
        timestamp,
        nonce,
        bytes(body),
    )
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "invalid signature")

    try:
        accepted = await _consume_nonce(
            system_id, nonce, now, signed_time + window + 1, window
        )
    except (RedisError, OSError, ValueError):
        raise HTTPException(503, "integration replay protection unavailable") from None
    if accepted == 0:
        raise HTTPException(401, "replayed nonce")
    if accepted != 1:
        raise HTTPException(429, "integration peer nonce quota exceeded")
    return ServiceIdentity(system_id=system_id)
