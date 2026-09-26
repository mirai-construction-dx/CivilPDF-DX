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
# Called from scripts/monitor-civilpdf.sh (every 5 min, after the healthcheck);
# the interval guard keeps the real check to once per
# CIVILPDF_ASSET_CHECK_INTERVAL minutes. When nothing could be checked (URL
# unset, container being recreated) it retries after CIVILPDF_ASSET_RETRY_INTERVAL.
#
# What is checked comes from the running backend container
# ($CIVILPDF_BACKEND_CONTAINER, default civilpdf-dx-backend-1): its
# APPS_RELEASE_BASE_URL and the asset filenames of the image actually serving
# /apps — not this checkout, which may be on another branch. Without the
# container, $APPS_RELEASE_BASE_URL and this checkout's list are used.
#
# Manual use:
#   ./scripts/editor-asset-watch.sh --force   # ignore the interval guard
#
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${CIVILPDF_MONITOR_STATE:-$HOME/.local/state/civildx-monitor}"
INTERVAL_MIN="${CIVILPDF_ASSET_CHECK_INTERVAL:-1440}"
RETRY_MIN="${CIVILPDF_ASSET_RETRY_INTERVAL:-60}"
PYTHON="${CIVILPDF_PYTHON:-python3}"
ALERT_CMD="${CIVILPDF_ALERT_NOTIFY:-$PROJECT_DIR/scripts/alert-notify.sh}"
CONTAINER="${CIVILPDF_BACKEND_CONTAINER:-civilpdf-dx-backend-1}"

[[ "$INTERVAL_MIN" =~ ^[0-9]+$ ]] || INTERVAL_MIN=1440
[[ "$RETRY_MIN" =~ ^[0-9]+$ ]] || RETRY_MIN=60

mkdir -p "$STATE_DIR"
NEXT_CHECK_FILE="$STATE_DIR/editor_assets_next_check_ts"
FAIL_FILE="$STATE_DIR/editor_assets_failing"
LOG_FILE="$STATE_DIR/monitor.log"

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "editor-assets: $*" >>"$LOG_FILE"; }
schedule_next() { echo $(( $(date +%s) + $1 * 60 )) >"$NEXT_CHECK_FILE"; }

now="$(date +%s)"
if [[ "${1:-}" != "--force" && -f "$NEXT_CHECK_FILE" ]]; then
  next="$(cat "$NEXT_CHECK_FILE")"
  # A corrupt state file must not stop the watch forever.
  [[ "$next" =~ ^[0-9]+$ ]] || next=0
  if (( now < next )); then
    exit 0
  fi
fi

base_url=""
filenames=""
if command -v docker >/dev/null 2>&1 \
  && container_env="$(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null)"; then
  base_url="$(printf '%s\n' "$container_env" | sed -n 's/^APPS_RELEASE_BASE_URL=//p' | head -n 1)"
  filenames="$(docker exec "$CONTAINER" python -c \
    'from api.apps import _build_packages; print(",".join(p.filename for p in _build_packages()))' 2>/dev/null)"
fi
base_url="${base_url:-${APPS_RELEASE_BASE_URL:-}}"

if [[ -z "$base_url" ]]; then
  schedule_next "$RETRY_MIN"
  log "skipped (APPS_RELEASE_BASE_URL not configured; retry in ${RETRY_MIN}m)"
  exit 0
fi

args=(--base-url "$base_url")
[[ -n "$filenames" ]] && args+=(--filenames "$filenames")
output="$("$PYTHON" "$PROJECT_DIR/scripts/check-editor-assets.py" "${args[@]}" 2>&1)"
rc=$?
schedule_next "$INTERVAL_MIN"

if (( rc == 0 )); then
  if [[ -f "$FAIL_FILE" ]]; then
    if "$ALERT_CMD" "[CivilPDF-DX] PDF Editor 配布リンク復旧" \
      "PDF Editor インストーラーの配布リンクが復旧しました。
配布元: $base_url
時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')"; then
      rm -f "$FAIL_FILE"
      log "recovered (notified)"
    else
      log "recovered but notification failed (will retry)"
    fi
  else
    log "ok"
  fi
  exit 0
fi

if (( rc == 1 )); then
  subject="[CivilPDF-DX] PDF Editor 配布リンク異常"
  summary="PDF Editor インストーラーの配布リンクを確認できませんでした（配信ページのダウンロードが 404 の可能性）。"
else
  subject="[CivilPDF-DX] PDF Editor 配布リンク検査の実行失敗"
  summary="配布リンク検査スクリプト自体が失敗しました（python/依存/引数の問題の可能性。リンクの状態は未確認）。"
fi

if [[ -f "$FAIL_FILE" ]]; then
  log "still failing since $(cat "$FAIL_FILE") (rc=$rc)"
  exit 0
fi
# Mark as notified only when the alert was actually sent, so it is retried.
if "$ALERT_CMD" "$subject" \
  "$summary
配布元: $base_url
時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')

-- check-editor-assets.py (rc=$rc) --
$output

対応: docs/deployment/app-distribution.md §3 / docs/operations/runbook.md §4.3"; then
  date '+%Y-%m-%d %H:%M:%S %Z' >"$FAIL_FILE"
  log "alert sent (rc=$rc)"
else
  schedule_next "$RETRY_MIN"
  log "alert failed to send (rc=$rc); retry in ${RETRY_MIN}m"
fi
exit 0
