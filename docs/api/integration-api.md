# Integration API — HMAC v1 discovery and signed ping

Status: implemented in this branch, not a claim of deployed inter-system connectivity.
IF-09 job execution is still **planned**. See [IF-09](cdp-if-09-contract.md)
and [ADR-0006](../architecture/ADR-0006-cross-repo-integration.md).

## Endpoints

| Endpoint | Authentication | Behavior |
| --- | --- | --- |
| `GET /api/v1/integration/catalog` | Public, read-only metadata | System/version, interface statuses and registry state; no business data or secrets |
| `GET /api/v1/integration/ping` | HMAC v1 | Signed connectivity probe; no data access or job execution |

`catalog` remains public even when signing is disabled. The manifest parity test
checks its declared interfaces. `ping` fails closed with **503** unless both peer
secrets and a shared nonce Redis URL are configured.

## Configuration

- `INTEGRATION_HMAC_SECRETS`: JSON map of system IDs to **distinct 64-character
  lowercase hex secrets**, generated using `openssl rand -hex 32`. At most 32 peers.
  Keep values outside Git in the environment-specific 0600 secret file.
- `INTEGRATION_NONCE_REDIS_URL`: dedicated shared Redis for all API workers.
  No local-cache fallback. Connection and command timeouts are 2 seconds.
- `INTEGRATION_CLOCK_SKEW_SECONDS`: 1–300 seconds, default 300.

Do not set secret JSON to an empty string. Absent secrets leave signed calls
unavailable; they do not grant anonymous access. This change does not create
Redis, configure secrets, or enable external publication automatically.

## HMAC v1 wire contract

Headers:

- `X-CivilPDF-System`: lowercase system ID, matching `[a-z][a-z0-9-]{1,39}`.
- `X-CivilPDF-Timestamp`: Unix epoch seconds, 1–12 decimal digits (not RFC3339).
- `X-CivilPDF-Nonce`: exactly 32 lowercase hex characters, randomly generated.
- `X-CivilPDF-Signature`: exactly 64 lowercase hex characters.

UTF-8 signing input, LF-separated with **no trailing LF**:

```text
SYSTEM
METHOD
PATH
TIMESTAMP
NONCE
SHA256_HEX(BODY)
```

`SYSTEM` is included so a changed identity header invalidates the signature.
`METHOD` is uppercase; `PATH` is the request URL path. Query strings are rejected
with 400, not silently excluded from the authenticated content. GET accepts no
body (413 if present). Reserved non-GET usage is limited to 4096 bytes before
buffering; no job endpoint is exposed in this change.

Reference signer (stdlib):

```python
import hashlib
import hmac
import time
import uuid


def sign(secret, system, method, path, body=b""):
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    canonical = (
        f"{system}\n{method.upper()}\n{path}\n{timestamp}\n{nonce}\n"
        f"{hashlib.sha256(body).hexdigest()}"
    )
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "X-CivilPDF-System": system,
        "X-CivilPDF-Timestamp": timestamp,
        "X-CivilPDF-Nonce": nonce,
        "X-CivilPDF-Signature": signature,
    }
```

## Replay protection and bounds

All workers atomically consume `(system, nonce)` in Redis via a Lua script. The
member is retained until **signed timestamp + skew + 1 second**, not arrival time
+ skew; this prevents future-dated requests from becoming replayable early.
Expired members are pruned atomically. Each peer has at most **1000 live nonces**;
additional requests fail with 429. The key expires after at most twice the skew
plus two seconds. Peer IDs are hashed in key names.

- Missing/malformed headers, bad signatures, stale timestamps and replay: **401**.
- Missing configuration or unavailable nonce Redis: **503** (never local fallback).
- Nonce quota: **429**.
- Middleware burst limits: ping 60/IP/minute, catalog 120/IP/minute **per worker**.
  These are not cluster-global rate limits; the nonce quota is shared.

Redis durability/eviction is an operational prerequisite: use a dedicated
no-eviction instance and preserve nonce records over restarts within the signing
window. This implementation does not guarantee replay resistance after loss of
Redis state. Leave signed calls disabled until that deployment requirement is
met. Job side effects also require persistent idempotency before IF-09 is enabled.

## Tests

API and adversarial tests cover public-catalog parity, exact-route service-auth
inventory, valid signing, identity/path binding, malformed/oversized headers,
query/body rejection, stale timestamps, future timestamp retention, replay,
Redis outage, missing configuration, quota and secret validation. An isolated
Redis subprocess test validates Lua atomicity, cross-process replay and TTL.
