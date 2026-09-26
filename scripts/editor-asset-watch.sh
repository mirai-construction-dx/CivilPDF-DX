#!/usr/bin/env bash
#
# CivilPDF-DX — daily watch of the PDF Editor installer download links.
#
# The /apps page hands out {APPS_RELEASE_BASE_URL}/{filename} links. If the
# release is moved, made private or deleted, those links 404 silently. This
# wrapper runs scripts/check-editor-assets.py at most once per interval and
# sends an alert email when an asset is unreachable (and once on recovery).
# It never affects the health monitor's exit status.
#
# Called from scripts/monitor-civilpdf.sh (every 5 min); the interval guard
# keeps the real check to once per CIVILPDF_ASSET_CHECK_INTERVAL minutes.
#
# Base URL resolution: $APPS_RELEASE_BASE_URL, else the running backend
# container's env ($CIVILPDF_BACKEND_CONTAINER, default civilpdf-dx-backend-1).
#
# Manual use:
#   ./scripts/editor-asset-watch.sh --force   # ignore the interval guard
#
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${CIVILPDF_MONITOR_STATE:-$HOME/.local/state/civildx-monitor}"
INTERVAL_MIN="${CIVILPDF_ASSET_CHECK_INTERVAL:-1440}"
PYTHON="${CIVILPDF_PYTHON:-python3}"
ALERT_CMD="${CIVILPDF_ALERT_NOTIFY:-$PROJECT_DIR/scripts/alert-notify.sh}"
CONTAINER="${CIVILPDF_BACKEND_CONTAINER:-civilpdf-dx-backend-1}"

mkdir -p "$STATE_DIR"
LAST_CHECK_FILE="$STATE_DIR/editor_assets_last_check_ts"
FAIL_FILE="$STATE_DIR/editor_assets_failing"
LOG_FILE="$STATE_DIR/monitor.log"

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "editor-assets: $*" >>"$LOG_FILE"; }

now="$(date +%s)"
if [[ "${1:-}" != "--force" && -f "$LAST_CHECK_FILE" ]]; then
  last="$(cat "$LAST_CHECK_FILE")"
  if (( now - last < INTERVAL_MIN * 60 )); then
    exit 0
  fi
fi

base_url="${APPS_RELEASE_BASE_URL:-}"
if [[ -z "$base_url" ]] && command -v docker >/dev/null 2>&1; then
  base_url="$(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
    | sed -n 's/^APPS_RELEASE_BASE_URL=//p' | head -n 1)"
fi

echo "$now" >"$LAST_CHECK_FILE"
if [[ -z "$base_url" ]]; then
  log "skipped (APPS_RELEASE_BASE_URL not configured)"
  exit 0
fi

output="$("$PYTHON" "$PROJECT_DIR/scripts/check-editor-assets.py" --base-url "$base_url" 2>&1)"
rc=$?

if (( rc == 0 )); then
  if [[ -f "$FAIL_FILE" ]]; then
    "$ALERT_CMD" "[CivilPDF-DX] PDF Editor 配布リンク復旧" \
      "PDF Editor インストーラーの配布リンクが復旧しました。
配布元: $base_url
時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')"
    rm -f "$FAIL_FILE"
    log "recovered"
  else
    log "ok"
  fi
  exit 0
fi

# rc=1 (asset failure) or anything unexpected: alert once per failing streak.
if [[ ! -f "$FAIL_FILE" ]]; then
  "$ALERT_CMD" "[CivilPDF-DX] PDF Editor 配布リンク異常" \
    "PDF Editor インストーラーの配布リンクを確認できませんでした（配信ページのダウンロードが 404 の可能性）。
配布元: $base_url
時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')

-- check-editor-assets.py (rc=$rc) --
$output

対応: docs/deployment/app-distribution.md §3 / docs/operations/runbook.md §4"
  date '+%Y-%m-%d %H:%M:%S %Z' >"$FAIL_FILE"
  log "alert sent (rc=$rc)"
else
  log "still failing since $(cat "$FAIL_FILE") (rc=$rc)"
fi
exit 0
