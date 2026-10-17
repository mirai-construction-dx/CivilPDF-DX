#!/usr/bin/env python3
"""Validate ``infra/integration/system.json`` (the cross-repo integration manifest).

The manifest declares CivilPDF-DX's system id, interfaces, data ownership and
registration state. It must not drift from the repository's version, staging
identifiers, local ADRs, or its own vocabulary.

Exit code 0 = valid, 1 = drift/invalid. Stdlib only; safe to run in CI.

Usage:
    python scripts/verify-integration-manifest.py
    python scripts/verify-integration-manifest.py --check-siblings
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SYSTEM_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
ADR_ID_RE = re.compile(r"^(MCDX-ADR|ADR)-\d{4}$")
INTERFACE_STATUS = {
    "implemented",
    "planned",
    "not-implemented",
    "not-integrated",
    "deprecated",
}
PROTOCOLS = {"http", "mcp", "event", "vendored-contracts"}
REGISTRATION_STATUS = {"pending", "registered", "not-required"}
REQUIRED_DOMAINS = {
    "documents",
    "revisions",
    "approvals",
    "audit-trail",
    "delivery-packages",
}


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate(root: Path, manifest_path: Path) -> list[str]:
    errors: list[str] = []

    def fail(message: str) -> None:
        errors.append(message)

    try:
        manifest = load_json(manifest_path)
    except OSError as exc:
        return [f"manifest is not readable: {exc}"]
    except json.JSONDecodeError as exc:
        return [f"manifest is not valid JSON: {exc}"]

    if not isinstance(manifest, dict):
        return ["manifest root must be an object"]

    # --- identity -----------------------------------------------------------
    system_id = manifest.get("systemId")
    if not isinstance(system_id, str) or not SYSTEM_ID_RE.match(system_id):
        fail(f"systemId must match {SYSTEM_ID_RE.pattern!r}, got {system_id!r}")

    version_file = root / "VERSION"
    if not version_file.is_file():
        fail("VERSION not found")
    else:
        version = version_file.read_text(encoding="utf-8").strip()
        if manifest.get("version") != version:
            fail(f"manifest version {manifest.get('version')!r} != VERSION {version!r}")

    repository = manifest.get("repository")
    if not isinstance(repository, str) or "/" not in repository:
        fail(f"repository must be 'owner/name', got {repository!r}")

    # --- staging identifiers -------------------------------------------------
    staging_rel = manifest.get("stagingIdentifiers")
    staging_path = root / str(staging_rel)
    if not isinstance(staging_rel, str) or not staging_path.is_file():
        fail(f"stagingIdentifiers {staging_rel!r} does not exist")
    else:
        try:
            identifiers = load_json(staging_path)
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"stagingIdentifiers is not readable JSON: {exc}")
        else:
            if identifiers.get("environment") != "staging":
                fail(
                    "stagingIdentifiers.environment must be 'staging', got "
                    f"{identifiers.get('environment')!r}"
                )
            production = identifiers.get("production") or {}
            if identifiers.get("tunnelName") == production.get("tunnelName"):
                fail("staging tunnelName must differ from production")
            if identifiers.get("databaseName") == production.get("databaseName"):
                fail("staging databaseName must differ from production")

    # --- ADRs ---------------------------------------------------------------
    adrs = manifest.get("adrs")
    if not isinstance(adrs, list) or not adrs:
        fail("adrs must be a non-empty list")
    else:
        for adr in adrs:
            if not isinstance(adr, dict):
                fail(f"adr entry must be an object, got {adr!r}")
                continue
            adr_id = adr.get("id")
            if not isinstance(adr_id, str) or not ADR_ID_RE.match(adr_id):
                fail(f"adr id must match {ADR_ID_RE.pattern!r}, got {adr_id!r}")
                continue
            if adr.get("conformance") not in {"conforms", "not-applicable", "pending"}:
                fail(f"{adr_id}: conformance must be conforms/not-applicable/pending")
            evidence = adr.get("evidence")
            if isinstance(evidence, str) and not (root / evidence).exists():
                fail(f"{adr_id}: evidence {evidence!r} does not exist")
            if adr.get("scope") == "local":
                matches = sorted((root / "docs" / "architecture").glob(f"{adr_id}-*.md"))
                if not matches:
                    fail(f"{adr_id}: local ADR file docs/architecture/{adr_id}-*.md not found")

    # --- interfaces ---------------------------------------------------------
    seen_ids: set[str] = set()
    for section in ("provides", "consumes"):
        interfaces = manifest.get(section)
        if not isinstance(interfaces, list) or not interfaces:
            fail(f"{section} must be a non-empty list")
            continue
        for entry in interfaces:
            if not isinstance(entry, dict):
                fail(f"{section} entry must be an object, got {entry!r}")
                continue
            interface_id = entry.get("id")
            if not isinstance(interface_id, str) or not interface_id:
                fail(f"{section}: interface id is required")
                continue
            if interface_id in seen_ids:
                fail(f"duplicate interface id {interface_id!r}")
            seen_ids.add(interface_id)
            if entry.get("protocol") not in PROTOCOLS:
                fail(
                    f"{interface_id}: protocol must be one of {sorted(PROTOCOLS)}, "
                    f"got {entry.get('protocol')!r}"
                )
            if entry.get("status") not in INTERFACE_STATUS:
                fail(
                    f"{interface_id}: status must be one of {sorted(INTERFACE_STATUS)}, "
                    f"got {entry.get('status')!r}"
                )
            contract = entry.get("contract")
            if isinstance(contract, str) and not (root / contract).exists():
                fail(f"{interface_id}: contract {contract!r} does not exist")

    # --- ownership ----------------------------------------------------------
    ownership = manifest.get("ownership")
    if not isinstance(ownership, dict) or not ownership:
        fail("ownership must be a non-empty object")
    else:
        missing = REQUIRED_DOMAINS - set(ownership)
        if missing:
            fail(f"ownership is missing domains: {sorted(missing)}")
        for domain, owner in ownership.items():
            if not isinstance(owner, str) or not owner:
                fail(f"ownership[{domain!r}] must be a non-empty string")

    # --- registration -------------------------------------------------------
    registration = manifest.get("registration")
    if not isinstance(registration, dict):
        fail("registration must be an object")
    else:
        for key, value in registration.items():
            if value not in REGISTRATION_STATUS:
                fail(
                    f"registration[{key!r}] must be one of {sorted(REGISTRATION_STATUS)}, "
                    f"got {value!r}"
                )

    return errors


def check_siblings(root: Path, manifest: dict, out: list[str]) -> None:
    """Best-effort check that sibling repositories know this system id.

    Only runs with --check-siblings (local development). A missing sibling is a
    SKIP, not a failure: CI checks out a single repository.
    """
    system_id = manifest.get("systemId", "")
    for entry in manifest.get("siblingChecks") or []:
        repo = entry.get("repo")
        rel = entry.get("file")
        if not repo or not rel:
            out.append(f"SKIP malformed siblingChecks entry: {entry!r}")
            continue
        candidate = root.parent / repo / rel
        if not candidate.is_file():
            out.append(f"SKIP {repo}/{rel} not present locally")
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if system_id and system_id in text:
            out.append(f"OK   {repo}/{rel} mentions {system_id}")
        else:
            out.append(f"INFO {repo}/{rel} does not mention {system_id} yet (registration PR pending)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--check-siblings", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else root / "infra" / "integration" / "system.json"

    errors = validate(root, manifest_path.resolve())
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        print("INTEGRATION MANIFEST: FAILED", file=sys.stderr)
        return 1

    if args.check_siblings:
        lines: list[str] = []
        try:
            manifest = load_json(manifest_path.resolve())
        except (OSError, json.JSONDecodeError):
            manifest = {}
        check_siblings(root, manifest if isinstance(manifest, dict) else {}, lines)
        for line in lines:
            print(line)

    print("INTEGRATION MANIFEST: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
