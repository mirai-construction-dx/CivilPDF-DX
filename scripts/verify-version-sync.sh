#!/usr/bin/env bash
#
# CivilPDF-DX — verify app version is consistent across repo docs/examples.
#
# Required: VERSION, deploy/civilpdf.env.example, .env.example,
# .env.prod.example, docs/operations/runbook.md.
# Warnings (non-blocking): config.py default, frontend package.json, git tag.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_FILE="$ROOT/VERSION"

if [[ ! -f "$VERSION_FILE" ]]; then
  echo "ERROR: $VERSION_FILE not found" >&2
  exit 1
fi

VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [[ -z "$VERSION" ]]; then
  echo "ERROR: $VERSION_FILE is empty" >&2
  exit 1
fi
echo "VERSION=$VERSION"

FAIL=0

check_contains() {
  local label="$1" file="$2" pattern="$3"
  if [[ -f "$file" ]] && grep -qF -- "$pattern" "$file"; then
    echo "OK   $label"
  else
    echo "FAIL $label (expected '$pattern' in $file)" >&2
    FAIL=1
  fi
}

check_contains "deploy env example" "$ROOT/deploy/civilpdf.env.example" "APP_VERSION=$VERSION"
check_contains "dev env example" "$ROOT/.env.example" "APP_VERSION=$VERSION"
check_contains "prod env example" "$ROOT/.env.prod.example" "APP_VERSION=$VERSION"
check_contains "runbook" "$ROOT/docs/operations/runbook.md" "現在 $VERSION"
check_contains "backend env example" "$ROOT/src/console/backend/.env.example" "APP_VERSION=$VERSION"

# Warnings — these are app-code/release metadata outside ops/docs scope.
if [[ -f "$ROOT/src/console/backend/config.py" ]] && \
   grep -q 'app_version: str = "0.1.0"' "$ROOT/src/console/backend/config.py"; then
  echo "WARN config.py default app_version is still 0.1.0 (dev default; sync at release)"
fi

# The UI badge reads the version from /health at runtime; a literal version
# string there goes stale (it said v0.4.2 until 0.10.0).
if grep -qE 'v[0-9]+\.[0-9]+\.[0-9]+ · Enterprise' "$ROOT/src/console/frontend/src/components/enterprise/EnterpriseLayout.tsx" 2>/dev/null; then
  echo "ERROR UI badge in EnterpriseLayout.tsx has a hard-coded version" >&2
  FAIL=1
fi

if [[ -f "$ROOT/src/console/frontend/package.json" ]] && \
   grep -q '"version": "0.0.0"' "$ROOT/src/console/frontend/package.json"; then
  echo "WARN frontend package.json version is still 0.0.0 (npm metadata; sync at release)"
fi

if ! git -C "$ROOT" rev-parse "v$VERSION" >/dev/null 2>&1; then
  echo "WARN git tag v$VERSION does not exist yet (expected at release time)"
fi

if [[ $FAIL -ne 0 ]]; then
  echo "VERSION SYNC: FAILED" >&2
  exit 1
fi

echo "VERSION SYNC: OK"
