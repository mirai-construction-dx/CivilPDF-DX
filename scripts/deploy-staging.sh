#!/usr/bin/env bash
#
# CivilPDF-DX — bring the STAGING stack up from the canonical env file.
#
# Idempotent. Safe to re-run. This is the single entry point for (re)deploying
# staging on the host: it reconciles the database role password with the secret
# in the canonical env file, rebuilds the images, waits for health, and runs the
# smoke check.
#
# Usage:
#   ./scripts/deploy-staging.sh            # full deploy (build + up + smoke)
#   ./scripts/deploy-staging.sh --no-build # restart containers only
#   ./scripts/deploy-staging.sh --dry-run  # print the plan, change nothing
#
# Environment:
#   STG_ENV_FILE   canonical staging env (default ~/.config/civilpdf/stg.env)
#
# Why the DB password reconcile exists: the PostgreSQL password is only consumed
# when the data volume is initialised. Rotating POSTGRES_PASSWORD in the env file
# without updating the role leaves the new containers unable to authenticate.
# `ALTER ROLE` over the container's local (trust) socket is idempotent and keeps
# the volume — and the synthetic demo data — intact.
#
# This script never writes the secret values anywhere; it only passes the file
# path to docker compose and reads a single value into a variable for ALTER ROLE.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STG_ENV="${STG_ENV_FILE:-$HOME/.config/civilpdf/stg.env}"
COMPOSE_FILE="$ROOT/docker-compose.staging.yml"
PROJECT="civilpdf-stg"
LOCAL_URL="${CIVILPDF_STG_URL:-http://127.0.0.1:18971}"

BUILD=1
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=0 ;;
    --dry-run) DRY_RUN=1 ;;
    -h | --help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      echo "unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

die() {
  echo "ERROR: $*" >&2
  exit 1
}
step() { printf '==> %s\n' "$*"; }

compose() {
  (cd "$ROOT" && STG_ENV_FILE="$STG_ENV" docker compose \
    --env-file "$STG_ENV" -f "$COMPOSE_FILE" "$@")
}

# --- 1. preflight ------------------------------------------------------------
step "preflight"
[[ -f "$COMPOSE_FILE" ]] || die "missing $COMPOSE_FILE"
[[ -f "$STG_ENV" ]] || die "missing canonical env $STG_ENV (create it from .env.stg.example, mode 0600)"
[[ "$(stat -c '%a' "$STG_ENV")" == "600" ]] || die "$STG_ENV must be mode 0600 (found $(stat -c '%a' "$STG_ENV"))"

# Refuse to run if the env points at production values. Staging must never
# share production identifiers (docs/deployment/staging-environment.md §3).
if grep -qE '^(POSTGRES_DB=civilpdf)$|^(FRONTEND_PORT=18970)$' "$STG_ENV"; then
  die "$STG_ENV contains production identifiers; refusing to deploy staging"
fi
for key in POSTGRES_PASSWORD SECRET_KEY TIMESTAMP_HMAC_KEY; do
  value="$(awk -F= -v k="$key" '$1==k {print substr($0, index($0, "=") + 1)}' "$STG_ENV")"
  [[ -n "$value" ]] || die "$key is empty in $STG_ENV"
  unset value
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  step "dry-run: would reconcile DB role password (if db container exists)"
  step "dry-run: would run docker compose up -d${BUILD:+ --build}"
  step "dry-run: would wait for healthy and run scripts/staging-smoke.py against $LOCAL_URL"
  exit 0
fi

# --- 2. reconcile the DB role password --------------------------------------
db_cid="$(docker ps -q \
  --filter "label=com.docker.compose.project=$PROJECT" \
  --filter "label=com.docker.compose.service=db" 2>/dev/null | head -1)"
if [[ -n "$db_cid" ]]; then
  step "reconcile database role password"
  db_user="$(awk -F= '$1=="POSTGRES_USER" {print substr($0, index($0, "=") + 1)}' "$STG_ENV")"
  db_name="$(awk -F= '$1=="POSTGRES_DB" {print substr($0, index($0, "=") + 1)}' "$STG_ENV")"
  db_pass="$(awk -F= '$1=="POSTGRES_PASSWORD" {print substr($0, index($0, "=") + 1)}' "$STG_ENV")"
  [[ -n "$db_user" && -n "$db_name" && -n "$db_pass" ]] || die "POSTGRES_USER/DB/PASSWORD must be set"
  # Local socket inside the container is trust-authenticated, so this works even
  # when the current password is unknown/rotated.
  printf "ALTER ROLE %s WITH PASSWORD '%s';\n" "$db_user" "$db_pass" |
    docker exec -i "$db_cid" psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -q
  unset db_pass
  echo "    database role reconciled with $STG_ENV"
else
  step "database container not running yet; password applies on first init"
fi

# --- 3. up / build -----------------------------------------------------------
if [[ "$BUILD" -eq 1 ]]; then
  step "docker compose up -d --build (project $PROJECT)"
  compose up -d --build
else
  step "docker compose up -d (project $PROJECT)"
  compose up -d
fi

# --- 4. wait for health ------------------------------------------------------
step "wait for /health to report environment=staging"
deadline=$((SECONDS + 300))
while ((SECONDS < deadline)); do
  env_value="$(curl -fsS --max-time 5 "$LOCAL_URL/health" 2>/dev/null |
    python3 -c 'import json,sys;print(json.load(sys.stdin).get("environment",""))' 2>/dev/null || true)"
  if [[ "$env_value" == "staging" ]]; then
    echo "    /health environment=staging"
    break
  fi
  sleep 5
done
[[ "${env_value:-}" == "staging" ]] || die "staging did not become healthy within 300s (last environment='${env_value:-none}')"

# --- 5. smoke ----------------------------------------------------------------
step "staging smoke"
(cd "$ROOT" && BASE_URL="$LOCAL_URL" python3 scripts/staging-smoke.py)

step "done: staging is up on $LOCAL_URL (loopback only)"
