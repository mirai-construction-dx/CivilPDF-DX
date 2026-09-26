#!/usr/bin/env bash
#
# CivilPDF-DX — verify app version is consistent across repo docs/examples.
#
# Required: VERSION, env examples (deploy/, root dev/prod, backend), runbook,
# config.py default, MVP compose + unit, UI badge free of hard-coded versions.
# Warnings (non-blocking): frontend package.json, git tag.
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
  # Whole-line match so APP_VERSION=1.0.10 does not satisfy 1.0.1 and a
  # commented-out value does not count.
  if [[ -f "$file" ]] && grep -qxF -- "$pattern" "$file"; then
    echo "OK   $label"
  else
    echo "FAIL $label (expected '$pattern' in $file)" >&2
    FAIL=1
  fi
}

check_contains "deploy env example" "$ROOT/deploy/civilpdf.env.example" "APP_VERSION=$VERSION"
check_contains "dev env example" "$ROOT/.env.example" "APP_VERSION=$VERSION"
check_contains "prod env example" "$ROOT/.env.prod.example" "APP_VERSION=$VERSION"
check_contains_substr() {
  local label="$1" file="$2" pattern="$3"
  if [[ -f "$file" ]] && grep -qF -- "$pattern" "$file"; then
    echo "OK   $label"
  else
    echo "FAIL $label (expected '$pattern' in $file)" >&2
    FAIL=1
  fi
}

check_contains_substr "runbook" "$ROOT/docs/operations/runbook.md" "現在 $VERSION"
check_contains "backend env example" "$ROOT/src/console/backend/.env.example" "APP_VERSION=$VERSION"
check_contains "config.py default" "$ROOT/src/console/backend/config.py" "    app_version: str = \"$VERSION\""
check_contains "MVP compose" "$ROOT/docker-compose.mvp.yml" "      APP_VERSION: $VERSION"
check_contains "MVP backend unit" "$ROOT/deploy/civilpdf-mvp-backend.service" "Environment=APP_VERSION=$VERSION"

# Warnings — release metadata outside ops/docs scope.
# The UI badge reads the version from /health at runtime; a literal version
# string there goes stale (it said v0.4.2 until 0.10.0).
BADGE_FILE="$ROOT/src/console/frontend/src/components/enterprise/EnterpriseLayout.tsx"
if [[ ! -f "$BADGE_FILE" ]]; then
  echo "FAIL badge check: $BADGE_FILE not found (moved? update this script)" >&2
  FAIL=1
elif grep -qE 'v[0-9]+\.[0-9]+\.[0-9]+[^"`]*Enterprise|"v[0-9]+\.[0-9]+\.[0-9]+"' "$BADGE_FILE"; then
  echo "FAIL UI badge in EnterpriseLayout.tsx has a hard-coded version" >&2
  FAIL=1
else
  echo "OK   UI badge reads the running version (/health)"
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
