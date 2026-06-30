#!/usr/bin/env bash
#
# Wipe all ERP business data on production before a legacy import.
# Keeps user logins and company branding. Does NOT delete media/ uploads.
#
# Usage (on PythonAnywhere):
#   cd ~/Sama-Acc
#   ./deploy/wipe_for_import.sh              # preview counts only
#   ./deploy/wipe_for_import.sh --execute    # actually delete (irreversible)
#
set -euo pipefail

PROJECT_DIR="/home/Samatours2026/Sama-Acc"
VENV_DIR="/home/Samatours2026/.virtualenvs/sama-accounting"
ENV_FILE="${PROJECT_DIR}/deploy/production.env"
CONFIRM_PHRASE="DELETE ALL BUSINESS DATA"

log() { printf '\n==> %s\n' "$1"; }
die() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

EXECUTE=0
EXTRA_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

if [[ ! -d "$PROJECT_DIR" ]]; then
  die "Project folder not found: $PROJECT_DIR"
fi
cd "$PROJECT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  die "Missing $ENV_FILE"
fi
if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  die "Virtualenv not found: $VENV_DIR"
fi

load_env_file() {
  local file="$1"
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line//$'\r'/}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"
      if [[ "$val" =~ ^\'(.*)\'$ ]]; then
        val="${BASH_REMATCH[1]}"
      elif [[ "$val" =~ ^\"(.*)\"$ ]]; then
        val="${BASH_REMATCH[1]}"
      fi
      export "$key=$val"
    fi
  done < "$file"
}

log "Loading production environment"
load_env_file "$ENV_FILE"
export DJANGO_SETTINGS_MODULE=config.settings.production

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [[ "$EXECUTE" -eq 0 ]]; then
  log "Dry run — showing what would be deleted"
  python manage.py wipe_business_data --dry-run "${EXTRA_ARGS[@]}"
  printf '\nTo actually delete, run:\n  ./deploy/wipe_for_import.sh --execute\n'
  exit 0
fi

log "WIPING business data (irreversible)"
python manage.py wipe_business_data --confirm "$CONFIRM_PHRASE" "${EXTRA_ARGS[@]}"

log "Done. Run import when the full backup is ready."
