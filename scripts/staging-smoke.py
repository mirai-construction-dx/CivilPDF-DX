#!/usr/bin/env python3
"""End-to-end smoke checks for the CivilPDF-DX STAGING environment.

Runs against the staging frontend (nginx) which reverse-proxies ``/api/`` and
``/health`` to the backend. Unlike ``scripts/mvp-smoke.py`` this script *asserts
the environment identifier*: staging must report ``environment == "staging"`` on
``/health``, so a misconfigured stack pointing at production/MVP fails loudly
instead of passing.

Staging is seeded with synthetic demo data (``scripts/seed_demo_data.py``), so
the well-known demo admin is the default login. Override with
``STAGING_ADMIN_EMAIL`` / ``STAGING_ADMIN_PASSWORD`` (CI uses GitHub Environment
``staging`` secrets). ``AUTH_BYPASS`` is NOT assumed.

Usage:
    # local staging stack
    python scripts/staging-smoke.py
    # public staging URL (via Cloudflare Tunnel + Access service token)
    BASE_URL=https://civilpdf-stg.mirai-dx-platform.com python scripts/staging-smoke.py

Exit code is non-zero when any check fails.
"""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:18971").rstrip("/")
ADMIN_EMAIL = os.environ.get("STAGING_ADMIN_EMAIL", "admin@demo.civilpdf.example")
ADMIN_PASSWORD = os.environ.get("STAGING_ADMIN_PASSWORD", "CivilPDF-Demo-2026!")
EXPECTED_ENV = os.environ.get("STAGING_EXPECTED_ENVIRONMENT", "staging")

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label} {detail}")
    if not condition:
        FAILURES.append(label)


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        # 1. Environment identity — the whole point of staging. A production or
        #    MVP endpoint answering here must fail this check.
        health = client.get("/health")
        is_json = health.headers.get("content-type", "").startswith("application/json")
        body = health.json() if is_json else {}
        check(
            "health status",
            health.status_code == 200 and body.get("status") == "ok",
            f"status={health.status_code} env={body.get('environment')!r}",
        )
        check(
            "health environment is staging",
            body.get("environment") == EXPECTED_ENV,
            f"got={body.get('environment')!r} want={EXPECTED_ENV!r}",
        )

        # 2. Authentication with real credentials (no AUTH_BYPASS assumption).
        login = client.post(
            "/api/v1/auth/token",
            data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        check("login", login.status_code == 200, f"status={login.status_code}")
        if login.status_code != 200:
            print(login.text[:300])
            return 1
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/v1/auth/me", headers=headers)
        ok = me.status_code == 200 and me.json().get("role") == "admin"
        check("auth/me is admin", ok, f"role={me.json().get('role')!r}")

        # 3. Seeded synthetic dataset is present.
        stats = client.get("/api/v1/stats/", headers=headers)
        ok = stats.status_code == 200 and stats.json().get("total_documents", 0) >= 20
        check(
            "stats (seeded documents)",
            ok,
            f"docs={stats.json().get('total_documents')}",
        )

        docs = client.get(
            "/api/v1/documents/",
            params={"include_meta": "true", "per_page": 5},
            headers=headers,
        )
        body = docs.json() if docs.status_code == 200 else {}
        ok = (
            docs.status_code == 200
            and len(body.get("items", [])) == 5
            and body.get("total", 0) >= 20
        )
        check(
            "documents list",
            ok,
            f"total={body.get('total')} items={len(body.get('items', []))}",
        )

        # 4. Audit hash chain intact after migrations + seed.
        verify = client.get("/api/v1/audit-logs/verify", headers=headers)
        ok = verify.status_code == 200 and verify.json().get("chain_valid") is True
        check(
            "audit hash chain",
            ok,
            f"records={verify.json().get('records_checked')}",
        )

    print(f"\nStaging smoke result: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
