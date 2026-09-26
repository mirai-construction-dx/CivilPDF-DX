#!/usr/bin/env bash
#
# CivilPDF-DX — periodic production monitor with external alerting.
#
# Runs the healthcheck and, when the service is DOWN, sends an email alert
# (throttled to once per ALERT_MIN_INTERVAL_MINUTES). When the service
# recovers, sends a recovery notification once.
#
# Intended to run every few minutes from a systemd timer:
#   deploy/civilpdf-monitor.service + deploy/civilpdf-monitor.timer
#
# Manual use:
#   ./scripts/monitor-civilpdf.sh          # check + alert on failure
#   ./scripts/monitor-civilpdf.sh --test   # send a test alert email
#
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${CIVILPDF_MONITOR_STATE:-$HOME/.local/state/civildx-monitor}"
ALERT_MIN_INTERVAL="${CIVILPDF_ALERT_MIN_INTERVAL:-30}"

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

# Daily PDF Editor download-link watch, run after the healthcheck on every exit
# path (self-throttled; the trap does not change the monitor's exit status).
trap '"$PROJECT_DIR/scripts/editor-asset-watch.sh" || true' EXIT

now="$(date +%s)"
if "$PROJECT_DIR/scripts/healthcheck-civilpdf.sh" --quiet; then
  if [[ -f "$DOWN_FILE" ]]; then
    down_since="$(cat "$DOWN_FILE")"
    "$PROJECT_DIR/scripts/alert-notify.sh" \
      "[CivilPDF-DX] 復旧通知" \
      "サービスが復旧しました。
停止開始: $down_since
復旧時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')
確認: ./scripts/healthcheck-civilpdf.sh"
    log "recovery alert sent (down since $down_since)"
    rm -f "$DOWN_FILE" "$LAST_ALERT_FILE"
  else
    log "healthy"
  fi
  exit 0
fi

# Service is down — alert with throttling.
[[ -f "$DOWN_FILE" ]] || date '+%Y-%m-%d %H:%M:%S %Z' >"$DOWN_FILE"
last=0
[[ -f "$LAST_ALERT_FILE" ]] && last="$(cat "$LAST_ALERT_FILE")"
elapsed=$((now - last))
if (( elapsed >= ALERT_MIN_INTERVAL * 60 )); then
  if ! details="$(cd "$PROJECT_DIR" && ./scripts/healthcheck-civilpdf.sh 2>&1)"; then
    details="${details:-healthcheck exited non-zero}"
  fi
  "$PROJECT_DIR/scripts/alert-notify.sh" \
    "[CivilPDF-DX] 異常検知" \
    "CivilPDF-DX のヘルスチェックに失敗しました。
時刻: $(date '+%Y-%m-%d %H:%M:%S %Z')
ホスト: $(hostname)

-- healthcheck details --
$details

確認/復旧手順: docs/operations/runbook.md"
  log "alert sent (healthcheck failed)"
  date +%s >"$LAST_ALERT_FILE"
else
  log "still down (last alert ${elapsed}s ago, throttled)"
fi
exit 1
