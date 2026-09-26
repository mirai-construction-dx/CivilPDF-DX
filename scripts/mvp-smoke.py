#!/usr/bin/env python3
"""End-to-end smoke checks for the CivilPDF-DX MVP environment.

Verifies the seeded demo dataset across the real HTTP API: authentication,
dashboard stats, document list/search, workflows, notifications, audit log
chain and CSV exports. Runs against either the local backend or the public
MVP URL (both expose the same /api/v1 prefix).

Usage:
    # local backend
    python scripts/mvp-smoke.py
    # public MVP URL (via Cloudflare Tunnel)
    BASE_URL=https://civilpdf-mvp.mirai-dx-platform.com python scripts/mvp-smoke.py

Exit code is non-zero when any check fails.
"""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8181").rstrip("/")
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "admin@demo.civilpdf.example")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "CivilPDF-Demo-2026!")

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label} {detail}")
    if not condition:
        FAILURES.append(label)


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        # /health is only reachable on the backend directly; behind the frontend
        # preview proxy use an unauthenticated API call to prove reachability.
        probe = client.get("/health")
        if probe.headers.get("content-type", "").startswith("application/json"):
            check(
                "health",
                probe.status_code == 200 and probe.json().get("status") == "ok",
            )
        else:
            probe = client.get("/api/v1/auth/me")
            check("api reachable", probe.status_code == 401)

        login = client.post(
            "/api/v1/auth/token",
            data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
        )
        check("login", login.status_code == 200, f"status={login.status_code}")
        if login.status_code != 200:
            print(login.text[:300])
            return 1
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/v1/auth/me", headers=headers)
        check("auth/me", me.status_code == 200 and me.json()["role"] == "admin")

        stats = client.get("/api/v1/stats/", headers=headers)
        ok = stats.status_code == 200 and stats.json().get("total_documents", 0) >= 20
        check("stats", ok, f"docs={stats.json().get('total_documents')}")

        docs = client.get(
            "/api/v1/documents/",
            params={"include_meta": "true", "per_page": 5},
            headers=headers,
        )
        body = docs.json()
        ok = (
            docs.status_code == 200
            and len(body.get("items", [])) == 5
            and body.get("total", 0) >= 20
            and body.get("pages", 0) >= 4
        )
        check("documents pagination", ok, f"total={body.get('total')}")

        search = client.get(
            "/api/v1/search/documents",
            params={"q": "橋梁", "mode": "keyword"},
            headers=headers,
        )
        ok = search.status_code == 200 and search.json().get("total", 0) >= 1
        check("full-text search", ok, f"hits={search.json().get('total')}")

        workflows = client.get("/api/v1/workflows/", headers=headers)
        ok = workflows.status_code == 200 and len(workflows.json()) >= 4
        check("workflows", ok, f"count={len(workflows.json())}")

        unread = client.get("/api/v1/notifications/unread-count", headers=headers)
        ok = unread.status_code == 200 and unread.json().get("unread", 0) >= 1
        check("notifications", ok, f"unread={unread.json().get('unread')}")

        audit = client.get(
            "/api/v1/audit-logs/", params={"per_page": 3}, headers=headers
        )
        ok = audit.status_code == 200 and audit.json().get("total", 0) >= 1
        check("audit logs", ok, f"total={audit.json().get('total')}")

        verify = client.get("/api/v1/audit-logs/verify", headers=headers)
        ok = verify.status_code == 200 and verify.json().get("chain_valid") is True
        check("audit hash chain", ok, f"records={verify.json().get('records_checked')}")

        audit_csv = client.get("/api/v1/audit-logs/export.csv", headers=headers)
        ok = (
            audit_csv.status_code == 200
            and audit_csv.content.startswith(b"\xef\xbb\xbf")
            and b"sequence_number" in audit_csv.content
        )
        check("audit CSV export", ok, f"bytes={len(audit_csv.content)}")

        docs_csv = client.get("/api/v1/documents/export.csv", headers=headers)
        ok = (
            docs_csv.status_code == 200
            and docs_csv.content.startswith(b"\xef\xbb\xbf")
            and b"project_code" in docs_csv.content
        )
        check("documents CSV export", ok, f"bytes={len(docs_csv.content)}")

        perm = client.get("/api/v1/users/permissions-report", headers=headers)
        ok = perm.status_code == 200 and perm.json().get("total", 0) >= 5
        check("permissions report", ok, f"total={perm.json().get('total')}")

        dx_sync = client.get("/api/v1/stats/dx-sync", headers=headers)
        ok = dx_sync.status_code == 200 and dx_sync.json().get("total", 0) >= 5
        check("dx-sync metrics", ok, f"total={dx_sync.json().get('total')}")

        # App distribution: Windows-only installers, macOS announced as pending.
        apps = client.get("/api/v1/apps/releases", headers=headers)
        try:
            body = apps.json() if apps.status_code == 200 else {}
        except ValueError:  # e.g. a proxy answering with the SPA's HTML
            body = {}
        platforms = {p.get("platform") for p in body.get("packages", [])}
        pending = [p.get("platform") for p in body.get("pending_platforms", [])]
        ok = (
            apps.status_code == 200
            and platforms == {"windows"}
            and pending == ["macos"]
        )
        check(
            "apps distribution (windows only)",
            ok,
            f"status={apps.status_code} platforms={sorted(platforms)} pending={pending}",
        )

        # RBAC: a viewer must not be able to read the admin-only audit log.
        viewer_login = client.post(
            "/api/v1/auth/token",
            data={
                "username": "viewer@demo.civilpdf.example",
                "password": DEMO_PASSWORD,
            },
        )
        viewer_token = (
            viewer_login.json().get("access_token")
            if viewer_login.status_code == 200
            else None
        )
        if viewer_token:
            viewer_audit = client.get(
                "/api/v1/audit-logs/",
                headers={"Authorization": f"Bearer {viewer_token}"},
            )
            check(
                "RBAC audit deny",
                viewer_audit.status_code == 403,
                f"status={viewer_audit.status_code}",
            )
        else:
            check("RBAC audit deny", False, "viewer login failed")

    print(f"\nSmoke result: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
