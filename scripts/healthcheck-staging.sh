#!/usr/bin/env bash
#
# CivilPDF-DX — STAGING health check.
#
# Verifies the staging compose stack WITHOUT touching production. Exit 0 = healthy,
# non-zero = degraded/down.
#
# Checks:
#   1. the three staging containers (db / backend / frontend) are running and,
#      where a healthcheck is defined, healthy;
#   2. `GET /health` reports `environment == "staging"` (catches a production or
#      MVP stack answering on the staging port);
#   3. the frontend answers HTTP 200;
#   4. backend readiness (`/health/ready`, which runs `SELECT 1`) succeeds.
#
# Usage:
#   ./scripts/healthcheck-staging.sh
#   ./scripts/healthcheck-staging.sh --quiet
#
# Environment:
#   CIVILPDF_STG_PROJECT   compose project name (default civilpdf-stg)
#   CIVILPDF_STG_URL       local staging base URL (default http://127.0.0.1:18971)
#
# This script never reads the staging env file and never passes it to a process:
# it uses docker label filters and the loopback HTTP endpoint only.
#
set -uo pipefail

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

PROJECT="${CIVILPDF_STG_PROJECT:-civilpdf-stg}"
BASE_URL="${CIVILPDF_STG_URL:-http://127.0.0.1:18971}"
PROD_PORT="18970"

FAIL=0
fail() {
  echo "FAIL $*" >&2
  FAIL=1
}
ok() {
  [[ $QUIET -eq 0 ]] && echo "OK   $*"
  return 0
}

container_id() {
  docker ps -q \
    --filter "label=com.docker.compose.project=$PROJECT" \
    --filter "label=com.docker.compose.service=$1" 2>/dev/null | head -1
}

# --- 0. fail closed if pointed at production --------------------------------
if [[ "$BASE_URL" == *":$PROD_PORT"* ]]; then
  fail "CIVILPDF_STG_URL points at the production port ($PROD_PORT); refusing to report staging health"
  exit 1
fi

# --- 1. containers -----------------------------------------------------------
for svc in db backend frontend; do
  cid="$(container_id "$svc")"
  if [[ -z "$cid" ]]; then
    fail "$svc container not running (project=$PROJECT)"
    continue
  fi
  state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo none)"
  if [[ "$state" != "running" ]]; then
    fail "$svc state=$state"
    continue
  fi
  if [[ "$health" == "unhealthy" ]]; then
    fail "$svc health=$health"
    continue
  fi
  # "starting" is the normal state during Docker's start_period / before the
  # first successful healthcheck (e.g. right after deploy-staging.sh recreates
  # the container). Treating it as DOWN makes the 5-minute monitor raise a false
  # alert when its tick lands within that window. Docker itself moves a
  # genuinely broken container to "unhealthy" after `retries`, which we fail on.
  if [[ "$health" == "starting" ]]; then
    ok "$svc running (health=starting)"
    continue
  fi
  ok "$svc running (health=$health)"
done

# --- 2. /health identity ------------------------------------------------------
health_body="$(curl -fsS --max-time 10 "$BASE_URL/health" 2>/dev/null || true)"
if [[ -z "$health_body" ]]; then
  fail "/health unreachable ($BASE_URL/health)"
else
  environment="$(printf '%s' "$health_body" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("environment",""))' 2>/dev/null || true)"
  if [[ "$environment" == "staging" ]]; then
    ok "/health environment=staging"
  else
    fail "/health environment=${environment:-<missing>} (expected staging)"
  fi
fi

# --- 3. frontend --------------------------------------------------------------
frontend_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE_URL/" 2>/dev/null || true)"
if [[ "$frontend_code" == "200" ]]; then
  ok "frontend HTTP 200"
else
  fail "frontend expected 200, got ${frontend_code:-timeout}"
fi

# --- 4. backend readiness (DB SELECT 1) --------------------------------------
backend_cid="$(container_id backend)"
if [[ -z "$backend_cid" ]]; then
  fail "backend readiness skipped (container not found)"
else
  if docker exec "$backend_cid" python -c \
    'import sys,urllib.request; r=urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=5); sys.exit(0 if r.status == 200 else 1)' \
    >/dev/null 2>&1; then
    ok "backend readiness (DB) 200"
  else
    fail "backend readiness (DB) failed"
  fi
fi

exit "$FAIL"
