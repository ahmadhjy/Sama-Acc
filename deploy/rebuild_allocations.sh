#!/usr/bin/env bash
#
# Rebuild AR/AP payment allocations (production).
#
# Usage:
#   cd ~/Sama-Acc
#   bash deploy/rebuild_allocations.sh
#
set -euo pipefail

PROJECT_DIR="/home/Samatours2026/Sama-Acc"
VENV_DIR="/home/Samatours2026/.virtualenvs/sama-accounting"
ENV_FILE="${PROJECT_DIR}/deploy/production.env"

log() { printf '\n==> %s\n' "$1"; }
die() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

cd "$PROJECT_DIR" || die "Project folder not found: $PROJECT_DIR"
[[ -f "$ENV_FILE" ]] || die "Missing $ENV_FILE"
[[ -f "$VENV_DIR/bin/activate" ]] || die "Virtualenv not found: $VENV_DIR"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
set -a && source "$ENV_FILE" && set +a
export DJANGO_SETTINGS_MODULE=config.settings.production

log "Rebuilding payment allocations (oldest due-date FIFO)"
python manage.py rebuild_payment_allocations

log "Done."
