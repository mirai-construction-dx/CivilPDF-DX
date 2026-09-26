#!/usr/bin/env bash
#
# CivilPDF-DX — offsite backup sync (Cloudflare R2 / S3 via rclone).
#
# Requires:
#   - rclone configured with a remote (e.g. `rclone config`)
#   - Local backups produced by scripts/backup-production.sh
#
# Usage:
#   CIVILPDF_RCLONE_REMOTE=civildx-r2:civilpdf-backups ./scripts/backup-offsite.sh
#
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-$HOME/civildx-backups}"
RCLONE_REMOTE="${CIVILPDF_RCLONE_REMOTE:-}"
RCLONE_BIN="${RCLONE_BIN:-rclone}"

if [[ -z "$RCLONE_REMOTE" ]]; then
  echo "ERROR: CIVILPDF_RCLONE_REMOTE is not set (e.g. civildx-r2:civilpdf-backups)" >&2
  exit 1
fi

if ! command -v "$RCLONE_BIN" >/dev/null 2>&1; then
  echo "ERROR: rclone is not installed" >&2
  exit 1
fi

if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "ERROR: local backup root not found: $BACKUP_ROOT" >&2
  exit 1
fi

# Sync only complete snapshot directories (each has civilpdf_dev.db).
latest="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '2*' \
  -exec test -f '{}/civilpdf_dev.db' \; -printf '%T@ %p\n' \
  | sort -nr | head -1 | cut -d' ' -f2-)"

if [[ -z "$latest" ]]; then
  echo "ERROR: no valid backup snapshot found under $BACKUP_ROOT" >&2
  exit 1
fi

echo "Syncing $latest -> $RCLONE_REMOTE"
"$RCLONE_BIN" sync "$latest" "$RCLONE_REMOTE/$(basename "$latest")" --progress
echo "Offsite backup complete: $RCLONE_REMOTE/$(basename "$latest")"
