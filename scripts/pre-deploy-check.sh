#!/usr/bin/env bash
#
# CivilPDF-DX — read-only pre-deploy checks for the production checkout.
#
# Run this right before `docker compose -f docker-compose.prod.yml up -d --build`.
# It changes nothing: no fetch, no checkout, no docker writes. It prints
# PASS / WARN / FAIL per check and exits 1 when any check FAILs.
#
#   ./scripts/pre-deploy-check.sh
#
# Checks
#   1. checkout is on main and equals origin/main (via git ls-remote)
#   2. no tracked changes other than state.json (hook runtime log)
#   3. .env exists and is not readable by group/others (0600)
#   4. production health (scripts/healthcheck-civilpdf.sh, incl. backup freshness)
#   5. rollback image tags exist (civilpdf-dx-{backend,frontend}:pre-*)
#   6. when APPS_RELEASE_BASE_URL is set in .env: installer links and SHA-256
#
# Only APPS_* keys are read from .env; secret values are never printed.
#
# Overridable for tests: CIVILPDF_PROJECT_DIR, CIVILPDF_HEALTHCHECK,
# CIVILPDF_PYTHON, CIVILPDF_IMAGE_PREFIX.
#
set -uo pipefail

PROJECT_DIR="${CIVILPDF_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HEALTHCHECK="${CIVILPDF_HEALTHCHECK:-$PROJECT_DIR/scripts/healthcheck-civilpdf.sh}"
PYTHON="${CIVILPDF_PYTHON:-python3}"
IMAGE_PREFIX="${CIVILPDF_IMAGE_PREFIX:-civilpdf-dx}"
ENV_FILE="$PROJECT_DIR/.env"

fails=0
warns=0
pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; warns=$((warns + 1)); }
fail() { printf '[FAIL] %s\n' "$*"; fails=$((fails + 1)); }

cd "$PROJECT_DIR" || { echo "[FAIL] cannot cd to $PROJECT_DIR"; exit 1; }

# 1. branch and commit
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
head="$(git rev-parse HEAD 2>/dev/null)"
remote_main="$(git ls-remote origin refs/heads/main 2>/dev/null | cut -f1)"
if [[ "$branch" != "main" ]]; then
  fail "checkout is on '$branch', not main (compose builds from this working tree)"
elif [[ -z "$remote_main" ]]; then
  warn "could not read origin/main (network?); HEAD=${head:0:7}"
elif [[ "$head" != "$remote_main" ]]; then
  fail "HEAD ${head:0:7} != origin/main ${remote_main:0:7} (git pull --ff-only first)"
else
  pass "on main at origin/main ${head:0:7}"
fi

# 2. tracked changes
changed="$(git status --porcelain --untracked-files=no | awk '{print $2}' | grep -v '^state\.json$')"
if [[ -n "$changed" ]]; then
  fail "tracked changes besides state.json: $(echo "$changed" | tr '\n' ' ')"
else
  pass "no tracked changes (state.json hook log is tolerated)"
fi

# 3. .env
if [[ ! -f "$ENV_FILE" ]]; then
  fail ".env not found (compose reads secrets from it)"
else
  mode="$(stat -c '%a' "$ENV_FILE")"
  if [[ "${mode: -2}" != "00" ]]; then
    fail ".env mode is $mode; run: chmod 600 .env"
  else
    pass ".env present with mode $mode"
  fi
fi

# 4. health (includes backup freshness)
if "$HEALTHCHECK" --quiet >/dev/null 2>&1; then
  pass "healthcheck OK (services, DB readiness, backup freshness)"
else
  fail "healthcheck failed; run $HEALTHCHECK for details"
fi

# 5. rollback tags
missing_tags=""
for svc in backend frontend; do
  if ! docker image ls --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
    | grep -q "^${IMAGE_PREFIX}-${svc}:pre-"; then
    missing_tags+="$svc "
  fi
done
if [[ -n "$missing_tags" ]]; then
  warn "no rollback tag for: ${missing_tags}(docker tag ${IMAGE_PREFIX}-<svc>:latest ${IMAGE_PREFIX}-<svc>:pre-\$(date +%Y%m%d))"
else
  pass "rollback image tags present"
fi

# 6. installer links (APPS_* only; values are public URLs / checksums)
apps_env() { [[ -f "$ENV_FILE" ]] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1; }
base_url="$(apps_env APPS_RELEASE_BASE_URL)"
if [[ -z "$base_url" ]]; then
  pass "APPS_RELEASE_BASE_URL unset (downloads show 近日公開予定; link check skipped)"
else
  if APPS_SHA256_WIN_EXE="$(apps_env APPS_SHA256_WIN_EXE)" \
    APPS_SHA256_WIN_MSI="$(apps_env APPS_SHA256_WIN_MSI)" \
    "$PYTHON" "$PROJECT_DIR/scripts/check-editor-assets.py" --verify-sha256 \
    --base-url "$base_url" >/dev/null 2>&1; then
    pass "installer links reachable and checksums match ($base_url)"
  else
    fail "installer link/checksum check failed; run scripts/check-editor-assets.py --verify-sha256"
  fi
fi

echo "---"
echo "result: ${fails} fail, ${warns} warn"
(( fails == 0 ))
