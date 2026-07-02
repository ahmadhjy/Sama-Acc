#!/usr/bin/env bash
#
# Import SATO26 staging into production after wipe_business_data.
#
# Prerequisite: exports/sato26/staging/*.jsonl on the server (git pull or upload).
#
# Usage:
#   cd ~/Sama-Acc
#   ./deploy/import_sato26.sh
#   ./deploy/import_sato26.sh --dry-run
#
set -euo pipefail

PROJECT_DIR="/home/Samatours2026/Sama-Acc"
VENV_DIR="/home/Samatours2026/.virtualenvs/sama-accounting"
ENV_FILE="${PROJECT_DIR}/deploy/production.env"

log() { printf '\n==> %s\n' "$1"; }
die() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
  esac
done

cd "$PROJECT_DIR"
[[ -f "$ENV_FILE" ]] || die "Missing $ENV_FILE"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
set -a && source "$ENV_FILE" && set +a
export DJANGO_SETTINGS_MODULE=config.settings.production

STAGING="$PROJECT_DIR/exports/sato26/staging"
[[ -f "$STAGING/manifest.json" ]] || die "Staging not found at $STAGING — upload or extract first."

log "Seeding roles (idempotent)"
python manage.py seed_roles

log "Seeding destinations (idempotent)"
python manage.py seed_destinations

ARGS=(--import-only)
[[ "$DRY" -eq 1 ]] && ARGS+=(--dry-run)

log "Importing SATO26 staging"
python manage.py import_sato26 "${ARGS[@]}"

log "Done. Verify dashboard and a sample client statement."
