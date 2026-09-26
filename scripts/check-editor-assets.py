#!/usr/bin/env python3
"""Verify that every distributed PDF Editor installer is downloadable.

The console's /apps page hands out `{APPS_RELEASE_BASE_URL}/{filename}` links.
If the release is moved, made private or never uploaded, those links silently
404 (this happened when the old CivilPDF-Editor release became unreachable).
This script checks each distributed package with a HEAD request (following
redirects to the GitHub asset CDN) and, when APPS_SHA256_<PKG_ID> is set,
downloads the asset to verify its checksum.

Usage:
    APPS_RELEASE_BASE_URL=https://github.com/mirai-construction-dx/CivilPDF-DX/releases/download/editor-v1.12.6 \\
        python scripts/check-editor-assets.py
    python scripts/check-editor-assets.py --base-url <url> [--verify-sha256]

Exit code: 0 = all reachable, 1 = at least one failure, 3 = base URL unset
(2 is left to argparse usage errors).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import httpx

_BACKEND = Path(__file__).resolve().parents[1] / "src" / "console" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from api.apps import ReleasePackage, _build_packages  # noqa: E402


def check_package(
    client: httpx.Client, base_url: str, pkg: ReleasePackage, verify_sha256: bool
) -> str | None:
    """Return None when the package is reachable (and matches), else a reason."""
    url = f"{base_url}/{pkg.filename}"
    try:
        resp = client.head(url)
        if resp.status_code != 200:
            return f"HTTP {resp.status_code}"
        if verify_sha256 and pkg.sha256:
            digest = hashlib.sha256()
            with client.stream("GET", url) as stream:
                # An error page must not be reported as a checksum mismatch.
                if stream.status_code != 200:
                    return f"GET HTTP {stream.status_code}"
                for chunk in stream.iter_bytes():
                    digest.update(chunk)
            if digest.hexdigest().lower() != pkg.sha256.lower():
                return "sha256 mismatch"
    except httpx.HTTPError as exc:
        return f"request failed: {exc.__class__.__name__}"
    return None


def run(base_url: str, client: httpx.Client, verify_sha256: bool = False) -> int:
    failures = 0
    for pkg in _build_packages():
        reason = check_package(client, base_url, pkg, verify_sha256)
        if reason is None:
            # Make it visible when only reachability (not integrity) was checked.
            note = (
                " (sha256 not configured)" if verify_sha256 and not pkg.sha256 else ""
            )
            print(f"[PASS] {pkg.id} {pkg.filename}{note}")
        else:
            failures += 1
            print(f"[FAIL] {pkg.id} {pkg.filename} — {reason}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base-url",
        default=os.getenv("APPS_RELEASE_BASE_URL", ""),
        help="release asset base URL (default: $APPS_RELEASE_BASE_URL)",
    )
    parser.add_argument(
        "--verify-sha256",
        action="store_true",
        help="download assets and compare with APPS_SHA256_<PKG_ID> when set",
    )
    args = parser.parse_args(argv)
    base_url = args.base_url.rstrip("/")
    if not base_url:
        print("[SKIP] APPS_RELEASE_BASE_URL is not set (downloads show 近日公開予定)")
        return 3
    if not base_url.startswith("https://"):
        print(f"[FAIL] base URL must be https: {base_url}")
        return 1
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        return run(base_url, client, args.verify_sha256)


if __name__ == "__main__":
    sys.exit(main())
