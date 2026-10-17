#!/usr/bin/env bash
#
# CivilPDF-DX — periodic STAGING monitor with external alerting.
#
# Runs scripts/healthcheck-staging.sh and, when staging is DOWN, sends an email
# alert (throttled to once per ALERT_MIN_INTERVAL_MINUTES). On recovery it sends
# a single recovery notification. Intended for a systemd timer:
#   deploy/civilpdf-stg-monitor.service + deploy/civilpdf-stg-monitor.timer
#
# Staging is a pre-production verification surface, so a separate state directory
# and message prefix are used: an outage here must not be mistaken for a
# production incident (and vice versa).
#
# Manual use:
#   ./scripts/monitor-staging.sh          # check + alert on failure
#   ./scripts/monitor-staging.sh --test   # send a test alert email
#
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${CIVILPDF_STG_MONITOR_STATE:-$HOME/.local/state/civildx-stg-monitor}"
ALERT_MIN_INTERVAL="${CIVILPDF_ALERT_MIN_INTERVAL:-30}"
PREFIX="[CivilPDF-DX staging]"

mkdir -p "$STATE_DIR"
LAST_ALERT_FILE="$STATE_DIR/last_alert_ts"
DOWN_FILE="$STATE_DIR/down_since"
LOG_FILE="$STATE_DIR/monitor.log"

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >>"$LOG_FILE"; }

if [[ "${1:-}" == "--test" ]]; then
  "$PROJECT_DIR/scripts/alert-notify.sh" --test
  rc=$?
  log "test alert rc=$rc"
  exit $rc
fi

alert() {
  if "$PROJECT_DIR/scripts/alert-notify.sh" "$1" "$2"; then
    date +%s >"$LAST_ALERT_FILE"
    log "alert sent: $1"
  else
    log "alert FAILED: $1"
  fi
}

now="$(date +%s)"

if "$PROJECT_DIR/scripts/healthcheck-staging.sh" --quiet; then
  if [[ -f "$DOWN_FILE" ]]; then
    down_since="$(cat "$DOWN_FILE")"
    alert "$PREFIX 復旧通知" "staging が復旧しました。
停止開始: $down_since
復旧時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')
確認: ./scripts/healthcheck-staging.sh"
    rm -f "$DOWN_FILE" "$LAST_ALERT_FILE"
  else
    log "healthy"
  fi
  exit 0
fi

# Staging is down — alert with throttling.
[[ -f "$DOWN_FILE" ]] || date '+%Y-%m-%d %H:%M:%S %Z' >"$DOWN_FILE"
last=0
[[ -f "$LAST_ALERT_FILE" ]] && last="$(cat "$LAST_ALERT_FILE" 2>/dev/null || echo 0)"
if ((now - last >= ALERT_MIN_INTERVAL * 60)); then
  alert "$PREFIX 異常" "staging のヘルスチェックが失敗しています。
停止開始: $(cat "$DOWN_FILE")
確認時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')
確認: ./scripts/healthcheck-staging.sh
復旧手順: docs/deployment/staging-environment.md §7"
else
  log "down (alert throttled)"
fi
exit 1
